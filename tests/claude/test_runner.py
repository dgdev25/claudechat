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


@pytest.mark.live
def test_live_turn_streams_text_and_returns_session_id():
    from claudechat.claude.runner import ClaudeRunner

    runner = ClaudeRunner(Config(), internal_token="test-token")
    events = list(runner.stream("Say exactly: pipeline works."))
    text = "".join(event.text for event in events if event.kind == "text")
    results = [event for event in events if event.kind == "result"]
    assert "pipeline works" in text.lower()
    assert results and results[0].session_id
