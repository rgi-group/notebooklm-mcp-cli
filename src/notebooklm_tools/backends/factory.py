"""Backend factory — selects the engine and (optionally) wires fallback.

Selection (default keeps drop-in compatibility with upstream):
- ``NOTEBOOKLM_BACKEND=notebooklm`` (default) → the unofficial NotebookLM web client.
- ``NOTEBOOKLM_BACKEND=official``            → the google-genai backend.
- ``NOTEBOOKLM_OFFICIAL_FALLBACK=1``         → when the official backend raises
  ``UnsupportedOnBackend``, transparently retry the call on the NotebookLM client.

The factory returns an object the ``services/*`` layer can use as ``client``.
"""

from __future__ import annotations

import os
from typing import Any

from .errors import UnsupportedOnBackend

_VALID = {"notebooklm", "official"}


def get_backend_name() -> str:
    name = os.environ.get("NOTEBOOKLM_BACKEND", "notebooklm").strip().lower()
    return name if name in _VALID else "notebooklm"


def _build_notebooklm_client() -> Any:
    # Imported lazily to avoid a hard dependency cycle and to keep the official
    # backend usable without initializing cookie auth.
    from notebooklm_tools.core.client import NotebookLMClient

    return NotebookLMClient()


def _build_official_backend() -> Any:
    from .official import OfficialBackend

    return OfficialBackend()


class _FallbackProxy:
    """Routes calls to ``primary``; on UnsupportedOnBackend, retries on ``secondary``."""

    def __init__(self, primary: Any, secondary_factory: Any) -> None:
        self._primary = primary
        self._secondary_factory = secondary_factory
        self._secondary: Any = None

    def __getattr__(self, attr: str) -> Any:
        target = getattr(self._primary, attr)
        if not callable(target):
            return target

        def _wrapped(*args: Any, **kwargs: Any) -> Any:
            try:
                return target(*args, **kwargs)
            except UnsupportedOnBackend:
                if self._secondary is None:
                    self._secondary = self._secondary_factory()
                return getattr(self._secondary, attr)(*args, **kwargs)

        return _wrapped


def get_client() -> Any:
    """Return the active backend client per env configuration."""
    name = get_backend_name()
    if name == "official":
        official = _build_official_backend()
        if os.environ.get("NOTEBOOKLM_OFFICIAL_FALLBACK", "").lower() in {"1", "true", "yes"}:
            return _FallbackProxy(official, _build_notebooklm_client)
        return official
    return _build_notebooklm_client()
