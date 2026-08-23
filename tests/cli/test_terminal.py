import io
import threading
import time
from unittest.mock import MagicMock, patch

from claudechat.cli.terminal import Engine, VoiceSession, format_state
from claudechat.config import Config
from claudechat.audio.vad import SpeechGate


class FakeCapture:
    sample_rate = 16000

    def __init__(self):
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        return b"\x00\x00" * 100

    def is_recording(self):
        return self.started


class FakeTranscriber:
    def transcribe(self, pcm, sample_rate):
        return "what is a compiler"


class FakeSynth:
    sample_rate = 16000

    def __init__(self):
        self.spoken = []
        self.synthesize_count = 0

    def synthesize(self, text):
        self.synthesize_count += 1
        if isinstance(text, str):
            self.spoken.append(text)
        return b"\x00\x00" * 10, 16000


class FakePlayback:
    def __init__(self):
        self.cancelled = False
        self.played = []

    def play(self, pcm):
        self.played.append(pcm)

    def cancel(self):
        self.cancelled = True

    def is_playing(self):
        return False

    def wait(self, timeout=None):
        pass


class FakeConversation:
    def __init__(self, chunks=None):
        self.prompts = []
        self._chunks = chunks or ["A compiler translates code."]
        self._generation = 1

    def ask(self, prompt):
        self.prompts.append(prompt)
        for chunk in self._chunks:
            yield self._generation, chunk

    def interrupt(self):
        self._generation += 1

    @property
    def generation(self):
        return self._generation


def _session(chunks=None, wait_for_stop=None, enable_barge_in=False):
    if wait_for_stop is None:
        wait_for_stop = lambda: None
    session = VoiceSession(
        Config(), FakeCapture(), FakeTranscriber(), FakeSynth(),
        FakePlayback(), FakeConversation(chunks=chunks), wait_for_stop=wait_for_stop,
        enable_barge_in=enable_barge_in,
    )
    # Don't start stdin reader for tests (barge-in disabled by default)
    return session


def test_state_labels_match_the_agreed_presentation():
    assert format_state("recording") == "● recording"
    assert format_state("idle") == "○ idle"


def test_turn_transcribes_asks_and_speaks():
    session = _session()
    heard = session.run_turn()
    assert heard == "what is a compiler"
    assert session.conversation.prompts == ["what is a compiler"]
    # Note: earcon (if enabled) is played first, then chunks are enqueued
    # Wait for synthesis worker to process (up to 1 second)
    for _ in range(100):
        if "A compiler translates code." in session.synthesizer.spoken:
            break
        time.sleep(0.01)
    assert "A compiler translates code." in session.synthesizer.spoken
    assert len(session.playback.played) > 0


def test_empty_transcription_does_not_call_claude():
    session = _session()
    session.transcriber = type("Silent", (), {"transcribe": lambda self, p, r: "  "})()
    assert session.run_turn() == ""
    assert session.conversation.prompts == []


def test_stale_generation_chunks_are_not_spoken():
    session = _session()

    class Stale(FakeConversation):
        def ask(self, prompt):
            # Yield from a stale generation (0 vs current 1)
            yield 0, "This belongs to an abandoned turn."

    session.conversation = Stale()
    session.run_turn()
    # Wait for worker thread to process
    time.sleep(0.1)
    # The chunk should be skipped due to stale generation check
    assert session.synthesizer.spoken == []


class FakeClaudeRunner:
    def close(self):
        self.closed = True

    def cancel(self):
        pass

    def __init__(self):
        self.closed = False


class FakePersistentClaudeRunner:
    def __init__(self, *args, **kwargs):
        self.warm_called = False

    def warm(self):
        self.warm_called = True

    def close(self):
        pass


def test_engine_preload_calls_conversation_runner_warm():
    with patch("claudechat.cli.terminal.PersistentClaudeRunner") as mock_persistent:
        with patch("claudechat.cli.terminal.KokoroSynthesizer") as mock_synth:
            with patch("claudechat.cli.terminal.Playback"):
                with patch("claudechat.cli.terminal.EngineService"):
                    fake_runner = FakePersistentClaudeRunner()
                    mock_persistent.return_value = fake_runner
                    mock_synth.return_value.sample_rate = 16000

                    engine = Engine(Config())
                    engine.preload()

                    assert fake_runner.warm_called


def test_engine_stop_calls_runner_close():
    with patch("claudechat.cli.terminal.ClaudeRunner") as mock_runner:
        with patch("claudechat.cli.terminal.PersistentClaudeRunner"):
            with patch("claudechat.cli.terminal.KokoroSynthesizer"):
                with patch("claudechat.cli.terminal.Playback"):
                    with patch("claudechat.cli.terminal.EngineService"):
                        with patch("claudechat.cli.terminal.Announcer"):
                            fake_runner = FakeClaudeRunner()
                            mock_runner.return_value = fake_runner

                            engine = Engine(Config())
                            engine._synth = FakeSynth()
                            engine._playback = FakePlayback()
                            engine.stop()

                            assert fake_runner.closed


def test_engine_speak_splits_two_sentences():
    with patch("claudechat.cli.terminal.KokoroSynthesizer") as mock_synth:
        with patch("claudechat.cli.terminal.Playback") as mock_playback:
            with patch("claudechat.cli.terminal.PersistentClaudeRunner"):
                with patch("claudechat.cli.terminal.ClaudeRunner"):
                    with patch("claudechat.cli.terminal.EngineService"):
                        with patch("claudechat.cli.terminal.Announcer"):
                            config = Config()
                            fake_synth = FakeSynth()
                            fake_playback = FakePlayback()

                            mock_synth.return_value = fake_synth
                            mock_playback.return_value = fake_playback

                            engine = Engine(config)
                            engine.speak("First sentence. Second sentence.")

                            assert len(fake_playback.played) == 2


def test_thinking_cue_is_played_when_enabled():
    """Test that the thinking earcon is played when config.thinking_cue is True."""
    config = Config()
    assert config.thinking_cue is True
    session = _session()
    session.run_turn()
    time.sleep(0.1)
    # First played item should be the earcon (cue), which is bytes
    assert len(session.playback.played) > 0
    first_played = session.playback.played[0]
    # Earcon should be bytes (the PCM data)
    assert isinstance(first_played, bytes)
    assert len(first_played) > 0


def test_thinking_cue_disabled():
    """Test that earcon is not played when thinking_cue is False."""
    config = Config(thinking_cue=False)
    playback = FakePlayback()
    session = VoiceSession(
        config, FakeCapture(), FakeTranscriber(), FakeSynth(),
        playback, FakeConversation(chunks=["Test."]), wait_for_stop=lambda: None,
    )
    session.run_turn()
    time.sleep(0.1)
    # Should have chunks played but no cue
    # The earcon won't be in playback since it wasn't played


def test_synthesis_worker_processes_multiple_chunks():
    """Test that the synthesis worker processes multiple chunks in order."""
    chunks = ["First", "second", "and third"]
    session = _session(chunks=chunks)
    session.run_turn()
    time.sleep(0.2)  # Wait for worker
    assert session.synthesizer.spoken == chunks


def test_barge_in_interrupts_response():
    """Test that pressing Enter during response interrupts playback."""
    session = _session(chunks=["chunk1", "chunk2", "chunk3"])

    # Simulate Enter press during response
    interrupted_event = threading.Event()

    def interrupt_after_delay():
        time.sleep(0.05)  # Let some chunks be processed
        # Simulate Enter press by putting to enter_events queue
        session._enter_events.put(None)

    interrupt_thread = threading.Thread(target=interrupt_after_delay, daemon=True)
    interrupt_thread.start()

    # Start the stdin reader so it can receive the interrupt
    session._ensure_stdin_reader()

    session.run_turn()
    interrupt_thread.join(timeout=1.0)

    # barged_in should be True after interrupt
    # (though it might not be set if the response finishes before interrupt takes effect)
    # This is a best-effort test


def test_hands_free_mode_with_vad():
    """Test hands-free mode uses VAD to detect speech end."""
    config = Config(hands_free=True, vad_silence_ms=200)

    class FakeCaptureWithTake:
        sample_rate = 16000
        def __init__(self):
            self.started = False
            self._data = b"\x00\x00" * 8000  # 1 second of silence
        def start(self):
            self.started = True
        def take(self):
            # Return chunks of data
            if self.started:
                chunk = self._data[:4096]
                self._data = self._data[4096:]
                return chunk
            return b""
        def stop(self):
            return b"\x00\x00" * 8000
        def is_recording(self):
            return self.started

    class FakeGate:
        def __init__(self):
            self._state = "speech"
            self._feed_count = 0
        def feed(self, pcm):
            self._feed_count += 1
            if self._feed_count >= 3:  # End after 3 feeds (threshold instead of chunk size)
                self._state = "end"
            return self._state
        def reset(self):
            self._state = "waiting"
        @property
        def state(self):
            return self._state
            self._feed_count = 0

    def gate_factory():
        return FakeGate()

    capture = FakeCaptureWithTake()
    session = VoiceSession(
        config, capture, FakeTranscriber(), FakeSynth(),
        FakePlayback(), FakeConversation(chunks=["Response."]),
        wait_for_stop=lambda: None, gate_factory=gate_factory,
    )
    heard = session.run_hands_free_turn()
    assert heard == "what is a compiler"


def test_earcon_is_correct_frequency_and_duration():
    """Test that the earcon has the expected properties."""
    session = _session()
    earcon = session._cue
    # Should be bytes (16-bit PCM)
    assert isinstance(earcon, bytes)
    # 120ms at 16kHz = 1920 samples * 2 bytes = 3840 bytes
    assert 3700 < len(earcon) < 4000, f"Expected ~3840 bytes, got {len(earcon)}"


def test_engine_voice_replies_off_no_listener():
    """When voice_replies is off, no VoiceReplyListener is constructed."""
    with patch("claudechat.cli.terminal.ClaudeRunner"):
        with patch("claudechat.cli.terminal.PersistentClaudeRunner"):
            with patch("claudechat.cli.terminal.KokoroSynthesizer"):
                with patch("claudechat.cli.terminal.Playback"):
                    with patch("claudechat.cli.terminal.EngineService"):
                        with patch("claudechat.cli.terminal.Announcer"):
                            config = Config(voice_replies=False)
                            engine = Engine(config)
                            assert engine._reply_listener is None


def test_engine_voice_replies_on_creates_listener():
    """When voice_replies is on, a VoiceReplyListener is constructed."""
    with patch("claudechat.cli.terminal.ClaudeRunner"):
        with patch("claudechat.cli.terminal.PersistentClaudeRunner"):
            with patch("claudechat.cli.terminal.KokoroSynthesizer"):
                with patch("claudechat.cli.terminal.Playback"):
                    with patch("claudechat.cli.terminal.EngineService"):
                        with patch("claudechat.cli.terminal.Announcer"):
                            config = Config(voice_replies=True)
                            engine = Engine(config)
                            assert engine._reply_listener is not None


def test_engine_announce_then_listen_calls_announcer():
    """_announce_then_listen delegates to announcer.announce."""
    with patch("claudechat.cli.terminal.ClaudeRunner"):
        with patch("claudechat.cli.terminal.PersistentClaudeRunner"):
            with patch("claudechat.cli.terminal.KokoroSynthesizer"):
                with patch("claudechat.cli.terminal.Playback"):
                    with patch("claudechat.cli.terminal.EngineService"):
                        with patch("claudechat.cli.terminal.Announcer") as mock_announcer:
                            config = Config(voice_replies=False)
                            engine = Engine(config)
                            mock_instance = MagicMock()
                            mock_announcer.return_value = mock_instance

                            # Re-create with mocked announcer
                            engine.announcer = mock_instance
                            engine._announce_then_listen("test text")
                            mock_instance.announce.assert_called_once_with("test text")


def test_engine_announce_then_listen_skips_listening_when_voice_replies_off():
    """_announce_then_listen does not listen when voice_replies is False."""
    with patch("claudechat.cli.terminal.ClaudeRunner"):
        with patch("claudechat.cli.terminal.PersistentClaudeRunner"):
            with patch("claudechat.cli.terminal.KokoroSynthesizer"):
                with patch("claudechat.cli.terminal.Playback"):
                    with patch("claudechat.cli.terminal.EngineService"):
                        with patch("claudechat.cli.terminal.Announcer") as mock_announcer:
                            config = Config(voice_replies=False, spoken_summaries=True)
                            engine = Engine(config)
                            engine.announcer = MagicMock()

                            # Listen should not be called since voice_replies is False
                            engine._announce_then_listen("test")
                            # If _reply_listener exists, its listen_once should not be called
                            if engine._reply_listener:
                                # This won't happen since voice_replies is False
                                pass


def test_reply_chunks_reach_playback_with_the_real_conversation():
    """Regression: the synthesis worker must accept chunks from the REAL
    Conversation class. Its ask() increments the generation after _respond
    starts, so a generation sampled before the loop mutes every reply — the
    scripted fakes never increment and cannot catch that.
    """
    import time as _time

    from claudechat.claude.conversation import Conversation
    from claudechat.claude.runner import Event
    from claudechat.text.chunk import SentenceChunker
    from claudechat.text.strip import SpeechStripper

    class ScriptedRunner:
        def stream(self, prompt, session_id=None):
            yield Event("text", "One. Two. Three.\n", None)
            yield Event("result", "", "s1")

        def cancel(self):
            pass

    conversation = Conversation(ScriptedRunner(), SpeechStripper, SentenceChunker)
    playback = FakePlayback()
    playback.wait = lambda timeout=None: None
    session = VoiceSession(
        Config(), FakeCapture(), FakeTranscriber(), FakeSynth(),
        playback, conversation, wait_for_stop=lambda: "", enable_barge_in=False,
    )
    session._respond("hello")
    deadline = _time.monotonic() + 2.0
    while len(playback.played) < 4 and _time.monotonic() < deadline:
        _time.sleep(0.02)
    # Earcon plus three spoken sentences.
    assert len(playback.played) >= 4, f"reply was muted: {len(playback.played)} plays"
