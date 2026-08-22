from __future__ import annotations

import threading
from collections.abc import Iterator


class Conversation:
    """One ongoing voice conversation: session continuity plus cancellation."""

    def __init__(self, runner, stripper_factory, chunker_factory) -> None:
        self._runner, self._stripper_factory, self._chunker_factory = runner, stripper_factory, chunker_factory
        self._generation = 0
        self._session_id: str | None = None
        self._lock = threading.Lock()

    @property
    def generation(self) -> int:
        with self._lock: return self._generation

    @property
    def session_id(self) -> str | None: return self._session_id

    def ask(self, prompt: str) -> Iterator[tuple[int, str]]:
        with self._lock:
            self._generation += 1
            generation = self._generation
        stripper, chunker = self._stripper_factory(), self._chunker_factory()
        for event in self._runner.stream(prompt, session_id=self._session_id):
            if self.generation != generation: return
            if event.kind == "text":
                for chunk in chunker.feed(stripper.feed(event.text)):
                    if self.generation != generation: return
                    yield generation, chunk
            elif event.kind == "result" and event.session_id:
                self._session_id = event.session_id
        for chunk in chunker.feed(stripper.flush()) + chunker.flush():
            if self.generation != generation: return
            yield generation, chunk

    def interrupt(self) -> None:
        with self._lock: self._generation += 1
        self._runner.cancel()
