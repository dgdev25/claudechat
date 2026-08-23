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
# A line that so far is only fence-ish characters may still become a fence.
_PARTIAL_FENCE = re.compile(r"^\s*(`{1,3}|~{1,3})\s*$")


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
        self._emitted = 0
        self._fence_char: str | None = None

    def feed(self, fragment: str) -> str:
        self._buffer += fragment
        out: list[str] = []
        while "\n" in self._buffer:
            line, self._buffer = self._buffer.split("\n", 1)
            self._emitted = 0
            rendered = self._line(line)
            if rendered:
                out.append(rendered)

        # Release the unfinished line too, when it is safe to do so. Waiting for
        # a newline sounds harmless but defeats the whole streaming design: a
        # reply that is one long paragraph produces no newline until it ends, so
        # nothing could be spoken until Claude had finished writing. Measured at
        # over two seconds of dead air per turn.
        # Completed lines are separated by a space; the unfinished tail is NOT.
        # It continues the word already emitted, so inserting a separator here
        # splits words down the middle — "Sunlight" arrives as "Sunl ight".
        text = " ".join(out)
        if out:
            text += " "
        return text + self._safe_partial()

    def _safe_partial(self) -> str:
        """Render the trailing unfinished line, or "" if it cannot be judged yet.

        Held back when: inside a fenced block; the line so far could still turn
        into a fence marker; or an inline-code span is open, since its closing
        backtick has not arrived and emitting now would speak the backtick.
        """
        if self._in_fence:
            return ""
        pending = self._buffer
        if _PARTIAL_FENCE.match(pending):
            return ""
        if pending.count("`") % 2 == 1:
            return ""

        rendered = self._line(pending, keep_state=True)
        if len(rendered) <= self._emitted:
            return ""
        fresh, self._emitted = rendered[self._emitted:], len(rendered)
        return fresh

    def flush(self) -> str:
        remaining, self._buffer = self._buffer, ""
        emitted, self._emitted = self._emitted, 0
        if self._in_fence:
            return ""
        rendered = self._line(remaining)
        return rendered[emitted:].strip() if len(rendered) > emitted else ""

    def _line(self, line: str, keep_state: bool = False) -> str:
        # keep_state renders an unfinished line for early speech without
        # committing fence state: the same text arrives again once its newline
        # lands, and toggling twice would leave the fence tracking inverted.
        fence_match = _FENCE.match(line)
        if fence_match:
            fence_char = fence_match.group(1)[0]
            if keep_state:
                return ""
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
