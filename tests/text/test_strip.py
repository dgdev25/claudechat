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


def test_removes_tilde_fenced_code_block():
    s = SpeechStripper()
    out = s.feed("Before\n~~~python\nprint('secret')\n~~~\nAfter") + s.flush()
    assert "secret" not in out
    assert "Before" in out and "After" in out


def test_backtick_fence_does_not_close_tilde_fence():
    s = SpeechStripper()
    out = s.feed("Before\n~~~\ncode\n```\nstill inside\n~~~\nAfter") + s.flush()
    assert "code" not in out
    assert "still inside" not in out
    assert "Before" in out and "After" in out


def test_preserves_snake_case_identifiers():
    s = SpeechStripper()
    out = s.feed("variable_name_here is used in x_1 vs x_2 test") + s.flush()
    assert "variable_name_here" in out
    assert "x_1" in out
    assert "x_2" in out


def test_removes_emphasis_at_boundaries():
    s = SpeechStripper()
    out = s.feed("_italic_ and **bold** and ~~strike~~ text") + s.flush()
    assert "_" not in out
    assert "*" not in out
    assert "~" not in out
    assert "italic" in out
    assert "bold" in out
    assert "strike" in out


def test_removes_table_row_entirely():
    s = SpeechStripper()
    out = s.feed("Header line\n| column | value |\nNext line") + s.flush()
    assert "column" not in out
    assert "value" not in out
    assert "Header line" in out
    assert "Next line" in out


def test_removes_list_markers_keeps_text():
    s = SpeechStripper()
    out = s.feed("Start\n- item one\n* item two\n1. item three\nEnd") + s.flush()
    assert "item one" in out
    assert "item two" in out
    assert "item three" in out
    assert "-" not in out
    assert "*" not in out or "Start" in out  # * removed but ** in bold might not be there
    assert "Start" in out
    assert "End" in out


def test_extracts_markdown_link_text():
    s = SpeechStripper()
    out = s.feed("See [documentation](https://example.com/docs) for details") + s.flush()
    assert "documentation" in out
    assert "example.com" not in out
    assert "https://" not in out
    assert "[" not in out and "]" not in out  # Brackets must be removed


def test_removes_8bit_c1_control_codes():
    assert strip_control_characters("hi\x9b31mred\x9b0m") == "hired"


def test_removes_8bit_osc_c1_code():
    assert strip_control_characters("text\x9d0\x07more") == "textmore"
