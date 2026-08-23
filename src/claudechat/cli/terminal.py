from __future__ import annotations

import secrets
import sys
from collections.abc import Callable

from claudechat.audio.capture import Capture
from claudechat.audio.playback import Playback
from claudechat.claude.conversation import Conversation
from claudechat.claude.runner import ClaudeRunner
from claudechat.config import Config, load_config
from claudechat.engine.announce import Announcer
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
    ) -> None:
        self.config = config
        self.capture = capture
        self.transcriber = transcriber
        self.synthesizer = synthesizer
        self.playback = playback
        self.conversation = conversation
        self._wait_for_stop = wait_for_stop

    def _state(self, state: str) -> None:
        print(f"\r\x1b[2K\x1b[2m{format_state(state)}\x1b[0m", end="", flush=True)

    def run_turn(self) -> str:
        self._state("recording")
        self.capture.start()
        self._wait_for_stop()
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
        self._state("thinking")

        spoken_any = False
        for generation, chunk in self.conversation.ask(heard):
            if generation != self.conversation.generation:
                continue
            if not spoken_any:
                print(f"\r\x1b[2Kclaude: {chunk}", end="", flush=True)
                spoken_any = True
            else:
                print(f" {chunk}", end="", flush=True)
            pcm_out, _rate = self.synthesizer.synthesize(chunk)
            self.playback.play(pcm_out)
        if spoken_any:
            print()
        self._state("idle")
        return heard


class Engine:
    """Owns the long-lived pieces: models, socket service, and the token file."""

    def __init__(self, config: Config, config_provider=None) -> None:
        self.config = config
        self.token = secrets.token_hex(16)
        self._synth: KokoroSynthesizer | None = None
        self._playback: Playback | None = None
        self.runner = ClaudeRunner(config, self.token)
        self.announcer = Announcer(
            config_provider or config, self.runner, lambda text: self.speak(text)
        )
        self.service = EngineService(config, on_announce=self.announcer.announce)

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

    def stop(self) -> None:
        self.service.stop()
        if self._playback is not None:
            self._playback.cancel()
        self.runner.cancel()
        (self.config.runtime_dir / "token").unlink(missing_ok=True)

    def speak(self, text: str) -> None:
        if self._synth is None:
            self._synth = KokoroSynthesizer(self.config)
            self._playback = Playback(sample_rate=self._synth.sample_rate)
        pcm, _ = self._synth.synthesize(text)
        if self._playback is not None:
            self._playback.play(pcm)


def interactive_main() -> int:
    config = load_config()
    engine = Engine(config)
    engine.start()
    synthesizer = KokoroSynthesizer(config)
    session = VoiceSession(
        config,
        Capture(config),
        WhisperTranscriber(config),
        synthesizer,
        Playback(sample_rate=synthesizer.sample_rate),
        Conversation(engine.runner, SpeechStripper, SentenceChunker),
    )
    print("claudechat — toggle mode: press Enter to start recording, Enter again to stop. Ctrl-C to quit.")
    try:
        while True:
            input()
            session.run_turn()
    except (KeyboardInterrupt, EOFError):
        session.playback.cancel()
        session.capture.stop()
        engine.stop()
        print("\nstopped.")
        return 0


if __name__ == "__main__":
    sys.exit(interactive_main())
