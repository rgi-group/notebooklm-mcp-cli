"""Pluggable backends for the NotebookLM MCP (rgi-group hybrid fork).

Two engines, one tool surface:
- ``notebooklm`` — unofficial NotebookLM web API (cookie auth); all artifacts.
- ``official``   — google-genai SDK; automatable subset (audio TTS, report/query).

See docs/HYBRID_BACKEND_PLAN.md. Select via NOTEBOOKLM_BACKEND env var.
"""

from __future__ import annotations

from .errors import BackendError, UnsupportedOnBackend
from .factory import get_backend_name, get_client

__all__ = [
    "BackendError",
    "UnsupportedOnBackend",
    "get_backend_name",
    "get_client",
]
