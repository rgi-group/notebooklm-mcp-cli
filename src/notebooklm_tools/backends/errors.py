"""Backend selection / capability errors."""

from __future__ import annotations


class BackendError(Exception):
    """Base class for backend errors."""


class UnsupportedOnBackend(BackendError):
    """Raised when an operation is not supported by the active backend.

    The ``official`` (google-genai) backend only implements the automatable
    subset (audio TTS podcast, report/query, optionally Veo video). NotebookLM-
    specific artifacts (infographic, slide_deck, mind_map, quiz, flashcards,
    data_table) are not available on it. When NOTEBOOKLM_OFFICIAL_FALLBACK is
    set, the factory catches this and routes the call to the ``notebooklm``
    backend instead.
    """

    def __init__(self, operation: str, backend: str) -> None:
        self.operation = operation
        self.backend = backend
        super().__init__(
            f"Operation '{operation}' is not supported on the '{backend}' backend. "
            f"Use the 'notebooklm' backend, or set NOTEBOOKLM_OFFICIAL_FALLBACK=1 "
            f"to auto-fall back for unsupported operations."
        )
