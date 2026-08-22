from claudechat.cli.terminal import VoiceSession, format_state
from claudechat.config import Config


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

    def synthesize(self, text):
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


class FakeConversation:
    def __init__(self):
        self.prompts = []

    def ask(self, prompt):
        self.prompts.append(prompt)
        yield 1, "A compiler translates code."

    def interrupt(self):
        pass

    @property
    def generation(self):
        return 1


def _session():
    return VoiceSession(
        Config(), FakeCapture(), FakeTranscriber(), FakeSynth(),
        FakePlayback(), FakeConversation(), wait_for_stop=lambda: None,
    )


def test_state_labels_match_the_agreed_presentation():
    assert format_state("recording") == "● recording"
    assert format_state("idle") == "○ idle"


def test_turn_transcribes_asks_and_speaks():
    session = _session()
    heard = session.run_turn()
    assert heard == "what is a compiler"
    assert session.conversation.prompts == ["what is a compiler"]
    assert session.synthesizer.spoken == ["A compiler translates code."]
    assert session.playback.played


def test_empty_transcription_does_not_call_claude():
    session = _session()
    session.transcriber = type("Silent", (), {"transcribe": lambda self, p, r: "  "})()
    assert session.run_turn() == ""
    assert session.conversation.prompts == []


def test_stale_generation_chunks_are_not_spoken():
    session = _session()

    class Stale(FakeConversation):
        def ask(self, prompt):
            yield 0, "This belongs to an abandoned turn."

    session.conversation = Stale()
    session.run_turn()
    assert session.synthesizer.spoken == []
