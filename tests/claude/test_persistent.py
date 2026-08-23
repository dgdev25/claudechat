import subprocess

import pytest

from claudechat.claude.persistent import PersistentClaudeRunner
from claudechat.claude.runner import VOICE_SYSTEM_PROMPT
from claudechat.config import Config


def _claude_processes() -> int:
    result = subprocess.run(["pgrep", "-f", "claude -p"], capture_output=True, text=True)
    return len(result.stdout.split())


def test_argv_never_enables_tools_or_fail_open_permissions():
    """The persistent runner must inherit the same hard constraints.

    A second code path spawning Claude is a second chance to lose the context
    stripping and the fail-closed permission mode, which is exactly how a voice
    assistant quietly regains the ability to run commands.
    """
    runner = PersistentClaudeRunner(Config(), "token", VOICE_SYSTEM_PROMPT)
    argv = runner._argv()
    assert "--permission-mode" not in argv, "fail-open permission mode must stay absent"
    assert argv[argv.index("--tools") + 1] == "", "tools must be disabled"
    assert '{"mcpServers":{}}' in argv, "MCP servers must be stripped"
    assert "--strict-mcp-config" in argv
    assert "--disable-slash-commands" in argv
    assert "--exclude-dynamic-system-prompt-sections" in argv
    assert "--input-format" in argv and argv[argv.index("--input-format") + 1] == "stream-json"


def test_environment_carries_the_recursion_guard():
    runner = PersistentClaudeRunner(Config(), "secret-token", VOICE_SYSTEM_PROMPT)
    env = runner._environment()
    assert env["CLAUDECHAT_INTERNAL"] == "secret-token", (
        "without the marker the Stop hook fires on our own calls and loops"
    )
    assert "ANTHROPIC_API_KEY" not in env


def test_cancel_marks_the_turn_abandoned():
    runner = PersistentClaudeRunner(Config(), "token", VOICE_SYSTEM_PROMPT)
    assert not runner._cancelled.is_set()
    runner.cancel()
    assert runner._cancelled.is_set()


def test_close_is_safe_when_nothing_started():
    PersistentClaudeRunner(Config(), "token", VOICE_SYSTEM_PROMPT).close()


@pytest.mark.live
def test_consecutive_turns_reuse_one_process_and_get_faster():
    import time

    runner = PersistentClaudeRunner(Config(), "live-test", VOICE_SYSTEM_PROMPT)
    before = _claude_processes()
    try:
        timings = []
        for question in ("Say the word one.", "Say the word two.", "Say the word three."):
            start = time.perf_counter()
            first = None
            for event in runner.stream(question):
                if event.kind == "text" and event.text.strip() and first is None:
                    first = time.perf_counter() - start
            timings.append(first)
        assert all(t is not None for t in timings)
        # Later turns skip process startup, so they must beat the first.
        assert min(timings[1:]) < timings[0], f"no speed-up across turns: {timings}"
    finally:
        runner.close()
        time.sleep(2)
    assert _claude_processes() <= before, "process leaked after close"


@pytest.mark.live
def test_abandoned_turn_never_leaks_into_the_next_one():
    """Stopping mid-turn must not contaminate the following turn.

    Measured before this was fixed: a caller that took the first sentence and
    stopped iterating left unread output in the process, and the next turn read
    the tail of the abandoned reply — answering a question about clouds with
    "ue light reaches your eyes". Any turn that does not reach its result now
    drops the process.
    """
    runner = PersistentClaudeRunner(Config(), "leak-test", VOICE_SYSTEM_PROMPT)
    try:
        # Abandon a turn after the first token, as a barge-in would.
        stream = runner.stream("Name three colours, one per sentence.")
        for event in stream:
            if event.kind == "text" and event.text.strip():
                break
        stream.close()

        reply = "".join(
            e.text for e in runner.stream("Reply with exactly: clean.") if e.kind == "text"
        ).lower()
        assert "clean" in reply, f"next turn did not answer its own question: {reply!r}"
        for leaked in ("red", "blue", "green", "colour", "color"):
            assert leaked not in reply, f"tail of the abandoned turn leaked: {reply!r}"
    finally:
        runner.close()


def test_session_id_stored_and_resume_flag_appears():
    """Verify that session_id from result events is stored and --resume appears in _argv()."""
    runner = PersistentClaudeRunner(Config(), "token", VOICE_SYSTEM_PROMPT)
    # No session_id initially.
    assert "--resume" not in runner._argv()
    # Set session_id directly.
    runner._session_id = "test-session-123"
    argv = runner._argv()
    assert "--resume" in argv
    idx = argv.index("--resume")
    assert argv[idx + 1] == "test-session-123"


def test_close_clears_session_id():
    """Verify that close() clears the session_id so --resume does not appear."""
    runner = PersistentClaudeRunner(Config(), "token", VOICE_SYSTEM_PROMPT)
    runner._session_id = "test-session-456"
    assert "--resume" in runner._argv()
    runner.close()
    assert "--resume" not in runner._argv()


def test_warm_spawns_process_when_none_alive(monkeypatch):
    """Verify that warm() spawns a process when none exists."""
    from unittest.mock import MagicMock, PropertyMock

    # Mock subprocess.Popen to avoid actually spawning a process.
    fake_process = MagicMock()
    fake_process.poll.return_value = None  # Simulate a live process.
    fake_process.stdin = MagicMock()
    fake_process.stdout = MagicMock()

    popen_calls = []

    def fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        return fake_process

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    runner = PersistentClaudeRunner(Config(), "token", VOICE_SYSTEM_PROMPT)
    assert not popen_calls, "Popen should not be called until warm()"
    runner.warm()
    assert len(popen_calls) == 1, "warm() should spawn a process"


def test_warm_does_nothing_after_close(monkeypatch):
    """Verify that warm() spawns nothing after close() has been called."""
    from unittest.mock import MagicMock

    popen_calls = []

    def fake_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        fake_process = MagicMock()
        fake_process.poll.return_value = None
        return fake_process

    monkeypatch.setattr("subprocess.Popen", fake_popen)

    runner = PersistentClaudeRunner(Config(), "token", VOICE_SYSTEM_PROMPT)
    runner.close()
    runner.warm()
    assert not popen_calls, "warm() should not spawn after close()"
