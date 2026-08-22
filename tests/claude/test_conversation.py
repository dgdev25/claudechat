from claudechat.claude.conversation import Conversation
from claudechat.claude.runner import Event
from claudechat.text.chunk import SentenceChunker
from claudechat.text.strip import SpeechStripper


class FakeRunner:
    def __init__(self, events): self._events, self.cancelled = events, False
    def stream(self, prompt, system_prompt=None, session_id=None): yield from self._events
    def cancel(self): self.cancelled = True


def _conversation(events): return Conversation(FakeRunner(events), SpeechStripper, SentenceChunker)


def test_yields_speakable_chunks_tagged_with_generation():
    events = [Event("text", "Hello there. ", None), Event("text", "All done now. ", None), Event("result", "Hello there. All done now.", "sess-1")]
    out = list(_conversation(events).ask("hi"))
    assert [chunk for _, chunk in out] == ["Hello there.", "All done now."]
    assert {generation for generation, _ in out} == {1}


def test_records_session_id_for_the_next_turn():
    conversation = _conversation([Event("result", "done", "sess-42")]); list(conversation.ask("hi")); assert conversation.session_id == "sess-42"


def test_generation_increments_per_turn():
    conversation = _conversation([Event("result", "done", "s")]); list(conversation.ask("one")); list(conversation.ask("two")); assert conversation.generation == 2


def test_interrupt_cancels_the_runner_and_bumps_generation():
    conversation = _conversation([Event("result", "done", "s")]); before = conversation.generation; conversation.interrupt(); assert conversation.generation == before + 1; assert conversation._runner.cancelled is True


def test_code_blocks_are_never_spoken():
    events = [Event("text", "Here it is.\n```py\nsecret()\n```\nDone.\n", None), Event("result", "x", "s")]
    assert "secret" not in " ".join(chunk for _, chunk in _conversation(events).ask("hi"))
