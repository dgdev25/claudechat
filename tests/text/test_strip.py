from claudechat.text.strip import SpeechStripper, strip_control_characters


def test_removes_terminal_escape_sequences():
    assert strip_control_characters("hi\x1b[31mred\x07") == "hired"


def test_keeps_newlines_and_tabs_as_spaces():
    assert strip_control_characters("a\nb\tc") == "a b c"


def test_strips_markdown_emphasis_and_headings():
    s = SpeechStripper()
    out = s.feed("## **Bold** and _italic_ text") + s.flush()
    assert out.strip() == "Bold and italic text"


def test_removes_fenced_code_block():
    s = SpeechStripper()
    out = s.feed("Before\n```python\nprint('x')\n```\nAfter") + s.flush()
    assert "print" not in out
    assert "Before" in out and "After" in out


def test_fence_split_across_fragments_is_still_removed():
    s = SpeechStripper()
    out = s.feed("Intro\n```py\nsecret_code(") + s.feed(")\n```\nOutro") + s.flush()
    assert "secret_code" not in out
    assert "Intro" in out and "Outro" in out


def test_replaces_url_with_placeholder():
    s = SpeechStripper()
    out = s.feed("See https://example.com/x for more") + s.flush()
    assert "example.com" not in out
    assert "a link" in out


def test_inline_code_is_read_as_plain_words():
    s = SpeechStripper()
    out = s.feed("Run `pytest -v` now") + s.flush()
    assert "`" not in out
    assert "pytest" in out
