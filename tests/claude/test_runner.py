import json

import pytest

from claudechat.config import Config
from claudechat.claude.runner import Event, parse_stream_line


def test_extracts_text_delta():
    line = json.dumps({
        "type": "stream_event",
        "event": {"type": "content_block_delta", "delta": {"type": "text_delta", "text": "Hello"}},
    })
    assert parse_stream_line(line) == Event(kind="text", text="Hello", session_id=None)


def test_ignores_non_text_stream_events():
    line = json.dumps({"type": "stream_event", "event": {"type": "message_start"}})
    assert parse_stream_line(line) is None


def test_extracts_result_with_session_id():
    line = json.dumps({"type": "result", "subtype": "success", "result": "Full reply.", "session_id": "abc-123"})
    event = parse_stream_line(line)
    assert event.kind == "result"
    assert event.session_id == "abc-123"


def test_ignores_system_and_rate_limit_events():
    assert parse_stream_line(json.dumps({"type": "system", "subtype": "init"})) is None
    assert parse_stream_line(json.dumps({"type": "rate_limit_event"})) is None


def test_ignores_malformed_lines():
    assert parse_stream_line("not json") is None
    assert parse_stream_line("") is None


def test_runner_uses_config_model():
    from claudechat.claude.runner import ClaudeRunner

    config = Config(claude_model="opus")
    runner = ClaudeRunner(config, internal_token="test-token")
    argv = runner._argv("system", None)
    model_idx = argv.index("--model") + 1
    assert argv[model_idx] == "opus"


def test_runner_override_model_takes_precedence():
    from claudechat.claude.runner import ClaudeRunner

    config = Config(claude_model="sonnet")
    runner = ClaudeRunner(config, internal_token="test-token", model="haiku")
    argv = runner._argv("system", None)
    model_idx = argv.index("--model") + 1
    assert argv[model_idx] == "haiku"


def test_runner_default_model_when_none():
    from claudechat.claude.runner import ClaudeRunner

    config = Config(claude_model="opus")
    runner = ClaudeRunner(config, internal_token="test-token", model=None)
    argv = runner._argv("system", None)
    model_idx = argv.index("--model") + 1
    assert argv[model_idx] == "opus"


@pytest.mark.live
def test_live_turn_streams_text_and_returns_session_id():
    from claudechat.claude.runner import ClaudeRunner

    runner = ClaudeRunner(Config(), internal_token="test-token")
    events = list(runner.stream("Say exactly: pipeline works."))
    text = "".join(event.text for event in events if event.kind == "text")
    results = [event for event in events if event.kind == "result"]
    assert "pipeline works" in text.lower()
    assert results and results[0].session_id


class FakePopen:
    """Fake subprocess.Popen for testing."""

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.pid = 12345
        self.stdin = FakeFile()
        self.stdout = iter([])
        self._poll_result = None

    def poll(self):
        return self._poll_result

    def wait(self, timeout=None):
        pass


class FakeFile:
    """Fake file object for testing."""

    def __init__(self):
        self.written = []

    def write(self, text):
        self.written.append(text)

    def close(self):
        pass


def test_prewarm_spawns_process(monkeypatch):
    """prewarm() spawns exactly one process."""
    from claudechat.claude.runner import ClaudeRunner

    config = Config(claude_model="opus")
    runner = ClaudeRunner(config, internal_token="test-token")

    popen_calls = []

    def fake_popen_factory(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return FakePopen(*args, **kwargs)

    monkeypatch.setattr("subprocess.Popen", fake_popen_factory)
    monkeypatch.setattr("os.killpg", lambda pid, sig: None)
    monkeypatch.setattr("os.getpgid", lambda pid: pid)

    runner.prewarm()
    assert len(popen_calls) == 1


def test_prewarm_does_not_spawn_twice_with_same_prompt(monkeypatch):
    """Second prewarm() with the same prompt spawns nothing more."""
    from claudechat.claude.runner import ClaudeRunner

    config = Config(claude_model="opus")
    runner = ClaudeRunner(config, internal_token="test-token")

    popen_calls = []

    def fake_popen_factory(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return FakePopen(*args, **kwargs)

    monkeypatch.setattr("subprocess.Popen", fake_popen_factory)
    monkeypatch.setattr("os.killpg", lambda pid, sig: None)
    monkeypatch.setattr("os.getpgid", lambda pid: pid)

    runner.prewarm()
    assert len(popen_calls) == 1
    runner.prewarm()
    assert len(popen_calls) == 1  # No new spawn


def test_stream_reuses_stashed_process_with_matching_prompt(monkeypatch):
    """stream() after prewarm() with matching prompt reuses stashed process."""
    from claudechat.claude.runner import ClaudeRunner

    config = Config(claude_model="opus")
    runner = ClaudeRunner(config, internal_token="test-token")

    popen_calls = []

    def fake_popen_factory(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return FakePopen(*args, **kwargs)

    monkeypatch.setattr("subprocess.Popen", fake_popen_factory)
    monkeypatch.setattr("os.killpg", lambda pid, sig: None)
    monkeypatch.setattr("os.getpgid", lambda pid: pid)

    runner.prewarm()
    calls_before_stream = len(popen_calls)
    assert calls_before_stream == 1

    list(runner.stream("test prompt"))  # Consume the iterator
    calls_after_stream = len(popen_calls)
    # stream() should NOT spawn a new process (it should reuse the stashed one)
    assert calls_after_stream == calls_before_stream

    runner.close()  # Prevent daemon thread from spawning


def test_stream_discards_stash_with_different_prompt(monkeypatch):
    """stream() with different system_prompt doesn't reuse stash."""
    from claudechat.claude.runner import ClaudeRunner, VOICE_SYSTEM_PROMPT

    config = Config(claude_model="opus")
    runner = ClaudeRunner(config, internal_token="test-token")

    popen_calls = []

    def fake_popen_factory(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return FakePopen(*args, **kwargs)

    monkeypatch.setattr("subprocess.Popen", fake_popen_factory)
    monkeypatch.setattr("os.killpg", lambda pid, sig: None)
    monkeypatch.setattr("os.getpgid", lambda pid: pid)

    runner.prewarm()  # Stash with default prompt
    calls_before_stream = len(popen_calls)
    assert calls_before_stream == 1

    different_prompt = "A different system prompt"
    list(runner.stream("test prompt", system_prompt=different_prompt))
    calls_after_stream = len(popen_calls)
    # stream() with different prompt should discard stash and spawn a new process
    assert calls_after_stream == calls_before_stream + 1

    runner.close()  # Prevent daemon thread from spawning


def test_close_prevents_prewarm_spawns(monkeypatch):
    """close() prevents further prewarm spawns."""
    from claudechat.claude.runner import ClaudeRunner

    config = Config(claude_model="opus")
    runner = ClaudeRunner(config, internal_token="test-token")

    popen_calls = []

    def fake_popen_factory(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return FakePopen(*args, **kwargs)

    monkeypatch.setattr("subprocess.Popen", fake_popen_factory)
    monkeypatch.setattr("os.killpg", lambda pid, sig: None)
    monkeypatch.setattr("os.getpgid", lambda pid: pid)

    runner.close()
    runner.prewarm()
    assert len(popen_calls) == 0  # No spawn after close
