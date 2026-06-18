"""Official Google Gen AI backend (google-genai).

Stable, billable, SDK-native alternative to the unofficial NotebookLM web API.
Implements the automatable subset only:

- ``create_audio_overview`` → multi-speaker TTS podcast (newest Gemini Flash TTS).
- ``create_report``        → Files API + grounded generation.
- ``poll_studio_status``   → in-memory job table (TTS/Veo can run async).

Unsupported artifacts raise ``UnsupportedOnBackend`` (factory may auto-fall back
to the ``notebooklm`` backend when NOTEBOOKLM_OFFICIAL_FALLBACK=1).

Auth resolution (handled in __init__):
  1. Vertex: GOOGLE_GENAI_USE_VERTEXAI=true + GOOGLE_CLOUD_PROJECT/LOCATION (ADC), or
  2. AI Studio: GEMINI_API_KEY.

Phase 1 = skeleton (NotImplemented). Implementation lands in phases 2-3 per
docs/HYBRID_BACKEND_PLAN.md.
"""

from __future__ import annotations

import os
from typing import Any

from .errors import UnsupportedOnBackend

# Newest Gemini Flash ids — Chris prefers the latest Flash models. Override via env.
DEFAULT_TTS_MODEL = os.environ.get("NOTEBOOKLM_OFFICIAL_TTS_MODEL", "gemini-2.5-flash-preview-tts")
DEFAULT_TEXT_MODEL = os.environ.get("NOTEBOOKLM_OFFICIAL_TEXT_MODEL", "gemini-3.5-flash")
DEFAULT_VIDEO_MODEL = os.environ.get("NOTEBOOKLM_OFFICIAL_VIDEO_MODEL", "veo-3.1-generate-preview")


class OfficialBackend:
    """google-genai implementation of the automatable studio subset."""

    backend_name = "official"

    def __init__(self) -> None:
        # Lazy import so the package imports cleanly even without google-genai installed.
        try:
            from google import genai  # type: ignore
        except ImportError as e:  # pragma: no cover - env-dependent
            raise BackendError_import_hint() from e

        use_vertex = os.environ.get("GOOGLE_GENAI_USE_VERTEXAI", "").lower() in {"1", "true", "yes"}
        if use_vertex:
            # Vertex AI path — bills to the GCP project via ADC.
            self._client = genai.Client(
                vertexai=True,
                project=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                location=os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1"),
            )
        else:
            api_key = os.environ.get("GEMINI_API_KEY")
            if not api_key:
                raise RuntimeError(
                    "official backend needs GEMINI_API_KEY (aistudio.google.com) "
                    "or Vertex (GOOGLE_GENAI_USE_VERTEXAI=true + ADC). "
                    "See docs/HYBRID_BACKEND_PLAN.md."
                )
            self._client = genai.Client(api_key=api_key)

    # ---- supported subset (implemented in phases 2-3) ----

    def get_notebook_sources_with_types(self, notebook_id: str) -> list[dict[str, Any]]:
        # Official backend models "notebook" as a local source set keyed by notebook_id.
        raise NotImplementedError("phase 3: source registry for official backend")

    def create_audio_overview(self, notebook_id: str, **kwargs: Any) -> dict[str, Any] | None:
        # phase 2: build a 2-host dialogue script grounded on sources, then
        # DEFAULT_TTS_MODEL multi-speaker TTS → audio bytes → GCS → return url.
        raise NotImplementedError("phase 2: multi-speaker TTS podcast")

    def create_report(self, notebook_id: str, **kwargs: Any) -> dict[str, Any] | None:
        # phase 3: Files API upload + grounded generation on DEFAULT_TEXT_MODEL.
        raise NotImplementedError("phase 3: grounded report")

    def poll_studio_status(self, notebook_id: str) -> list[dict[str, Any]]:
        # phase 2: return the in-memory job table for this notebook_id.
        return []

    # ---- explicitly unsupported (NotebookLM-only) ----

    def create_video_overview(self, *a: Any, **k: Any) -> Any:
        # Optional future: route to Veo (DEFAULT_VIDEO_MODEL). Unsupported for now.
        raise UnsupportedOnBackend("video", self.backend_name)

    def create_infographic(self, *a: Any, **k: Any) -> Any:
        raise UnsupportedOnBackend("infographic", self.backend_name)

    def create_slide_deck(self, *a: Any, **k: Any) -> Any:
        raise UnsupportedOnBackend("slide_deck", self.backend_name)

    def generate_mind_map(self, *a: Any, **k: Any) -> Any:
        raise UnsupportedOnBackend("mind_map", self.backend_name)

    def create_quiz(self, *a: Any, **k: Any) -> Any:
        raise UnsupportedOnBackend("quiz", self.backend_name)

    def create_flashcards(self, *a: Any, **k: Any) -> Any:
        raise UnsupportedOnBackend("flashcards", self.backend_name)

    def create_data_table(self, *a: Any, **k: Any) -> Any:
        raise UnsupportedOnBackend("data_table", self.backend_name)


def BackendError_import_hint() -> RuntimeError:
    return RuntimeError(
        "official backend requires the google-genai SDK: pip install google-genai"
    )
