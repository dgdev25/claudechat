from __future__ import annotations

import re

_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")
_ESCAPE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(\x07|\x1b\\)|\x9b[0-9;?]*[ -/]*[@-~]|\x9d[^\x07\x9b]*(\x07|\x9b)")
_WHITESPACE_CONTROL = re.compile(r"[\n\r\t]+")

_FENCE = re.compile(r"^\s*(`{3}|~{3})")
_URL = re.compile(r"https?://\S+|www\.\S+")
_TABLE_ROW = re.compile(r"^\s*\|.*\|\s*$")
_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+")
_LIST_MARKER = re.compile(r"^\s*([-*+]|\d+[.)])\s+")
_EMPHASIS = re.compile(r"(\*\*|__|\*|~~|(?<!\w)_|_(?!\w))")
_INLINE_CODE = re.compile(r"`([^`]*)`")
_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")


def strip_control_characters(text: str) -> str:
    """Remove terminal escapes and control characters; keep readable whitespace."""
    text = _ESCAPE.sub("", text)
    text = _WHITESPACE_CONTROL.sub(" ", text)
    return _CONTROL.sub("", text)


class SpeechStripper:
    """Turn streamed markdown into text worth speaking.

    Stateful on purpose: a code fence can open in one fragment and close in
    another, so fence state must survive between feed() calls.
    """

    def __init__(self) -> None:
        self._buffer = ""
        self._in_fence = False
        self._fence_char: str | None = None

    def feed(self, fragment: str) -> str:
        self._buffer += fragment
        out: list[str] = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            rendered = self._line(line)
            if rendered:
                out.append(rendered)
        return " ".join(out) + (" " if out else "")

    def flush(self) -> str:
        remaining, self._buffer = self._buffer, ""
        if self._in_fence:
            return ""
        return self._line(remaining)

    def _line(self, line: str) -> str:
        fence_match = _FENCE.match(line)
        if fence_match:
            fence_char = fence_match.group(1)[0]
            if self._in_fence and self._fence_char == fence_char:
                self._in_fence = False
                self._fence_char = None
            elif not self._in_fence:
                self._in_fence = True
                self._fence_char = fence_char
            return ""
        if self._in_fence:
            return ""
        if _TABLE_ROW.match(line):
            return ""
        line = _LINK.sub(r"\1", line)
        line = _URL.sub("a link", line)
        line = _INLINE_CODE.sub(r"\1", line)
        line = _HEADING.sub("", line)
        line = _LIST_MARKER.sub("", line)
        line = _EMPHASIS.sub("", line)
        line = strip_control_characters(line)
        return " ".join(line.split())
