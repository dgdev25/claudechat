from __future__ import annotations

import re

_ABBREVIATIONS = {
    "mr", "mrs", "ms", "dr", "prof", "st", "jr", "sr",
    "e.g", "i.e", "etc", "vs", "approx", "fig", "no", "al",
}
_TERMINATOR = re.compile(r"([.!?])(\s)")


class SentenceChunker:
    """Split a stream of text into speakable chunks.

    The first chunk of a reply is released early — on a comma or a word count —
    so audio starts sooner. Later chunks wait for a real sentence end.
    """

    def __init__(self, first_chunk_min_chars: int = 10, first_chunk_max_words: int = 30) -> None:
        self._buffer = ""
        self._is_first = True
        self._min_chars = first_chunk_min_chars
        self._max_words = first_chunk_max_words

    def feed(self, text: str) -> list[str]:
        self._buffer += text
        chunks: list[str] = []
        while True:
            chunk = self._take()
            if chunk is None:
                break
            chunks.append(chunk)
        return chunks

    def flush(self) -> list[str]:
        remaining = self._buffer.strip()
        self._buffer = ""
        self._is_first = False
        return [remaining] if remaining else []

    def _take(self) -> str | None:
        if self._is_first:
            early = self._early_first_chunk()
            if early is not None:
                return early

        for match in _TERMINATOR.finditer(self._buffer):
            end = match.end(1)
            candidate = self._buffer[:end]
            if self._ends_in_abbreviation(candidate):
                continue
            self._buffer = self._buffer[match.end(2):]
            self._is_first = False
            return candidate.strip()

        return None

    def _early_first_chunk(self) -> str | None:
        comma = self._buffer.find(",")
        if comma >= self._min_chars:
            chunk = self._buffer[: comma + 1]
            self._buffer = self._buffer[comma + 1 :].lstrip()
            self._is_first = False
            return chunk.strip()

        words = self._buffer.split()
        if len(words) > self._max_words:
            chunk = " ".join(words[: self._max_words]) + ","
            self._buffer = " ".join(words[self._max_words :])
            self._is_first = False
            return chunk
        return None

    @staticmethod
    def _ends_in_abbreviation(candidate: str) -> bool:
        if not candidate.endswith("."):
            return False
        tail = candidate[:-1].split()
        if not tail:
            return False
        last = tail[-1].lower().strip("()[]\"'")
        if last in _ABBREVIATIONS:
            return True
        return bool(re.search(r"\d$", last))
