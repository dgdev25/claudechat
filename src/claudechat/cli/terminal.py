from __future__ import annotations

import queue
import secrets
import sys
import threading
import time
from collections.abc import Callable

import numpy as np

from claudechat.audio.capture import Capture
from claudechat.audio.playback import Playback
from claudechat.audio.vad import SpeechGate
from claudechat.claude.conversation import Conversation
from claudechat.claude.persistent import PersistentClaudeRunner
from claudechat.claude.runner import VOICE_SYSTEM_PROMPT, ClaudeRunner
from claudechat.config import Config, load_config
from claudechat.engine.announce import Announcer
from claudechat.engine.reply import VoiceReplyListener
from claudechat.engine.service import EngineService
from claudechat.speech.synthesizer import KokoroSynthesizer
from claudechat.speech.transcriber import WhisperTranscriber
from claudechat.text.chunk import SentenceChunker
from claudechat.text.strip import SpeechStripper, strip_control_characters

_STATE_MARKS = {
    "idle": "○", "recording": "●", "transcribing": "◐",
    "thinking": "◇", "speaking": "▶",
}


def format_state(state: str) -> str:
    return f"{_STATE_MARKS.get(state, '○')} {state}"


class VoiceSession:
    """One turn at a time: record, transcribe, ask, speak."""

    def __init__(
        self,
        config: Config,
        capture: Capture,
        transcriber: WhisperTranscriber,
        synthesizer: KokoroSynthesizer,
        playback: Playback,
        conversation: Conversation,
        wait_for_stop: Callable[[], str] = input,
        gate_factory: Callable[[], SpeechGate] | None = None,
        enable_barge_in: bool = True,
    ) -> None:
        self.config = config
        self.capture = capture
        self.transcriber = transcriber
        self.synthesizer = synthesizer
        self.playback = playback
        self.conversation = conversation
        self._wait_for_stop = wait_for_stop
        self._gate_factory = gate_factory or self._default_gate_factory
        self._enable_barge_in = enable_barge_in
        self.barged_in = False

        # Thinking earcon: 120ms @ 660Hz sine wave with fade
        self._cue = self._generate_earcon(120, 660)

        # Synthesis worker queue and thread
        self._current_generation = -1
        self._synth_queue: queue.Queue[str | None] = queue.Queue()
        self._synth_worker = threading.Thread(target=self._synthesis_worker, daemon=True)
        self._synth_worker.start()

        # Enter event queue for unified input handling
        self._enter_events: queue.Queue[None] = queue.Queue()
        self._stdin_reader: threading.Thread | None = None
        self._stdin_reader_started = False

        # Interrupt handling
        self._responding = threading.Event()
        self._interrupted = threading.Event()
        self._record_now = threading.Event()

    def _default_gate_factory(self) -> SpeechGate:
        return SpeechGate(
            sample_rate=self.capture.sample_rate,
            threshold=self.config.vad_threshold,
            silence_ms=self.config.vad_silence_ms,
        )

    def _generate_earcon(self, duration_ms: int, freq: float) -> bytes:
        """Generate a sine wave tone with linear fade in/out.

        Returns 16-bit mono PCM at the synthesizer's sample rate.
        """
        sample_rate = self.synthesizer.sample_rate
        samples = int(sample_rate * duration_ms / 1000)
        fade_samples = int(sample_rate * 20 / 1000)  # 20ms fade

        # Generate sine wave
        t = np.arange(samples, dtype=np.float32) / sample_rate
        wave = np.sin(2 * np.pi * freq * t) * 0.15

        # Apply fade-in and fade-out
        if fade_samples > 0:
            fade_in = np.linspace(0, 1, fade_samples, dtype=np.float32)
            fade_out = np.linspace(1, 0, fade_samples, dtype=np.float32)
            wave[:fade_samples] *= fade_in
            wave[-fade_samples:] *= fade_out

        # Convert to 16-bit PCM
        pcm = (wave * 32767).astype(np.int16).tobytes()
        return pcm

    def _ensure_stdin_reader(self) -> None:
        """Start the stdin reader thread lazily if not already running."""
        if self._stdin_reader_started:
            return
        self._stdin_reader_started = True

        def read_stdin() -> None:
            while True:
                try:
                    self._wait_for_stop()
                    self._enter_events.put(None)
                except (EOFError, KeyboardInterrupt):
                    break

        self._stdin_reader = threading.Thread(target=read_stdin, daemon=True)
        self._stdin_reader.start()

    def _wait_for_enter(self) -> None:
        """Wait for an Enter event (from either direct wait_for_stop or stdin reader)."""
        # For scripted tests where wait_for_stop returns immediately,
        # only use stdin reader if it was started
        if self._stdin_reader_started:
            self._enter_events.get()
        else:
            # Fallback for tests: use direct wait_for_stop
            self._wait_for_stop()

    def _state(self, state: str) -> None:
        print(f"\r\x1b[2K\x1b[2m{format_state(state)}\x1b[0m", end="", flush=True)

    def _synthesis_worker(self) -> None:
        """Synthesis worker thread: pop chunks, synthesize, play.

        Every popped item is acknowledged with task_done() so _respond can
        join() the queue — "queue empty" is not "synthesis finished": the last
        chunk is still inside Kokoro after its pop.
        """
        while True:
            try:
                chunk = self._synth_queue.get(timeout=5.0)
            except queue.Empty:
                continue
            try:
                if chunk is None:  # Poison pill for session shutdown
                    return
                if not isinstance(chunk, str):  # Sentinel for end-of-turn
                    continue
                # Stale generation check: skip chunks from an interrupted turn.
                if self.conversation.generation != self._current_generation:
                    continue
                pcm_out, _rate = self.synthesizer.synthesize(chunk)
                if self.conversation.generation != self._current_generation:
                    continue
                self.playback.play(pcm_out)
            finally:
                self._synth_queue.task_done()

    def _interrupt_response(self) -> None:
        """Interrupt the current response.

        An interrupt means the user wants to talk: the next run_turn skips its
        wait-for-Enter and records immediately.
        """
        self.conversation.interrupt()
        self.playback.cancel()
        self._interrupted.set()
        self._record_now.set()
        self.barged_in = True

    def _respond(self, heard: str) -> None:
        """Shared reply logic for both run_turn and run_hands_free_turn."""
        self._state("thinking")
        self._responding.set()
        self._current_generation = self.conversation.generation

        # Play thinking cue if enabled
        if self.config.thinking_cue:
            self.playback.play(self._cue)

        spoken_any = False
        self._interrupted.clear()

        # Set up barge-in listener if enabled and not in hands-free mode
        if self._enable_barge_in and not self.config.hands_free:
            listener_thread = threading.Thread(
                target=self._barge_in_listener, daemon=True
            )
            listener_thread.start()

        for generation, chunk in self.conversation.ask(heard):
            if self._interrupted.is_set():
                break
            if generation != self.conversation.generation:
                continue
            if not spoken_any:
                print(f"\r\x1b[2Kclaude: {chunk}", end="", flush=True)
                spoken_any = True
            else:
                print(f" {chunk}", end="", flush=True)
            self._synth_queue.put(chunk)

        # Block until the worker has acknowledged every queued chunk —
        # including synthesis of the last one, not just its pop.
        self._synth_queue.join()

        if spoken_any:
            print()

        self._responding.clear()

    def _barge_in_listener(self) -> None:
        """Listen for Enter while response is playing; interrupt if pressed."""
        self._ensure_stdin_reader()
        try:
            # Wait for Enter with a timeout while responding is set
            while self._responding.is_set():
                try:
                    self._enter_events.get(timeout=0.1)
                    if self._responding.is_set():
                        self._interrupt_response()
                    else:
                        # The reply ended in the same instant: this Enter was
                        # the user's "start recording" press — give it back.
                        self._enter_events.put(None)
                    return
                except queue.Empty:
                    pass
        except Exception:
            pass

    def run_turn(self) -> str:
        """Record, transcribe, ask, speak. Restart immediately after speaking."""
        # Check if we should start recording now (from a previous barge-in)
        if self._record_now.is_set():
            self._record_now.clear()
        else:
            # Wait for Enter to start recording
            self._state("idle")
            self._wait_for_enter()

        self._state("recording")
        self.capture.start()
        self._wait_for_enter()
        pcm = self.capture.stop()

        self._state("transcribing")
        heard = strip_control_characters(
            self.transcriber.transcribe(pcm, self.capture.sample_rate)
        ).strip()
        if not heard:
            self._state("idle")
            print("\r\x1b[2K(nothing heard)")
            return ""

        print(f"\r\x1b[2Kyou: {heard}")
        self._respond(heard)

        # Wait for playback to finish
        self.playback.wait(timeout=self.config.max_speech_seconds)
        self._state("idle")
        return heard

    def run_hands_free_turn(self) -> str:
        """Record with VAD, transcribe, ask, speak."""
        self._state("listening")
        self.capture.start()
        gate = self._gate_factory()
        accumulated = bytearray()

        start_time = time.monotonic()
        while time.monotonic() - start_time < self.config.max_recording_seconds:
            pcm = self.capture.take()
            if pcm:
                accumulated.extend(pcm)
                state = gate.feed(pcm)
                if state == "end":
                    break
            time.sleep(0.05)

        # Get remaining audio from capture
        full_pcm = self.capture.stop()

        # If no speech detected, return empty
        if gate.state == "waiting":
            self._state("idle")
            print("\r\x1b[2K(no speech detected)")
            return ""

        self._state("transcribing")
        heard = strip_control_characters(
            self.transcriber.transcribe(full_pcm, self.capture.sample_rate)
        ).strip()
        if not heard:
            self._state("idle")
            print("\r\x1b[2K(nothing heard)")
            return ""

        print(f"\r\x1b[2Kyou: {heard}")
        self._respond(heard)

        # Wait for playback to finish
        self.playback.wait(timeout=self.config.max_speech_seconds)
        self._state("idle")
        return heard


class Engine:
    """Owns the long-lived pieces: models, socket service, and the token file."""

    def __init__(self, config: Config, config_provider=None) -> None:
        self.config = config
        self.token = secrets.token_hex(16)
        self._synth: KokoroSynthesizer | None = None
        self._playback: Playback | None = None
        # Two runners on purpose.
        #
        # Conversation turns reuse one long-lived process: consecutive turns
        # drop from 2.5s to 1.3s to first token, and the conversation context is
        # wanted there anyway.
        #
        # Hook summaries do NOT reuse it. Each summary is independent, so a
        # shared process would accumulate unrelated replies and pay for that
        # context on every later summary.
        self.runner = ClaudeRunner(config, self.token, model=config.summary_model)
        self.conversation_runner = PersistentClaudeRunner(
            config, self.token, VOICE_SYSTEM_PROMPT
        )
        self.announcer = Announcer(
            config_provider or config, self.runner, lambda text: self.speak(text)
        )
        self._config_provider = config_provider
        self._reply_listener: VoiceReplyListener | None = None
        if config.voice_replies:
            self._reply_listener = VoiceReplyListener(
                config,
                capture_factory=lambda: Capture(config),
                transcriber_factory=lambda: WhisperTranscriber(config),
                gate_factory=lambda: SpeechGate(
                    sample_rate=Capture.sample_rate,
                    threshold=config.vad_threshold,
                    silence_ms=config.vad_silence_ms,
                ),
                speak=lambda text: self.speak(text),
            )
        self.service = EngineService(
            config,
            on_announce=self._announce_then_listen,
            on_drop=lambda: self.speak("Still working."),
        )

    def start(self) -> None:
        self.config.runtime_dir.mkdir(parents=True, exist_ok=True)
        self.config.runtime_dir.chmod(0o700)
        token_file = self.config.runtime_dir / "token"
        token_file.write_text(self.token)
        token_file.chmod(0o600)
        self.service.start()

    def preload(self) -> None:
        """Load the speech models now, so the first spoken reply is not delayed."""
        if self._synth is None:
            self._synth = KokoroSynthesizer(self.config)
            self._playback = Playback(sample_rate=self._synth.sample_rate)
        try:
            self.conversation_runner.warm()
        except Exception:
            pass

    @property
    def synthesizer(self) -> KokoroSynthesizer | None:
        return self._synth

    @property
    def playback(self) -> Playback | None:
        return self._playback

    def stop(self) -> None:
        self.service.stop()
        self.conversation_runner.close()
        if self._playback is not None:
            self._playback.cancel()
        self.runner.close()
        (self.config.runtime_dir / "token").unlink(missing_ok=True)

    def speak(self, text: str) -> None:
        if not text:
            return
        if self._synth is None:
            self._synth = KokoroSynthesizer(self.config)
            self._playback = Playback(sample_rate=self._synth.sample_rate)
        chunker = SentenceChunker(
            self.config.first_chunk_min_chars, self.config.first_chunk_max_words
        )
        chunks = chunker.feed(text) + chunker.flush()
        for chunk in chunks:
            pcm, _ = self._synth.synthesize(chunk)
            if self._playback is not None:
                self._playback.play(pcm)

    def _announce_then_listen(self, text: str) -> None:
        """Announce text, then listen for voice reply if enabled."""
        self.announcer.announce(text)

        # Re-read config to check if voice_replies is currently on
        cfg = self._config_provider() if self._config_provider and callable(self._config_provider) else self.config
        if not cfg.voice_replies or not cfg.spoken_summaries or self._reply_listener is None:
            return

        # Wait for playback to drain so microphone does not record the summary
        if self._playback is not None:
            self._playback.wait(timeout=cfg.max_speech_seconds)

        # Listen for voice reply
        self._reply_listener.listen_once()


def interactive_main() -> int:
    config = load_config()
    engine = Engine(config)
    engine.start()
    engine.preload()
    session = VoiceSession(
        config,
        Capture(config),
        WhisperTranscriber(config),
        engine.synthesizer,
        engine.playback,
        Conversation(engine.conversation_runner, SpeechStripper, lambda: SentenceChunker(config.first_chunk_min_chars, config.first_chunk_max_words)),
    )
    if config.hands_free:
        print("claudechat — hands-free mode: speak to record, silence to stop. Ctrl-C to quit.")
    else:
        print("claudechat — toggle mode: press Enter to start recording, Enter again to stop. Ctrl-C to quit.")
    try:
        if config.hands_free:
            while True:
                session.run_hands_free_turn()
        else:
            while True:
                session.run_turn()
    except (KeyboardInterrupt, EOFError):
        session.playback.cancel()
        session.capture.stop()
        engine.stop()
        print("\nstopped.")
        return 0


if __name__ == "__main__":
    sys.exit(interactive_main())
