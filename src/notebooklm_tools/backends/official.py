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
DEFAULT_TEXT_MODEL = os.environ.get("NOTEBOOKLM_OFFICIAL_TEXT_MODEL", "gemini-2.5-flash")
DEFAULT_VIDEO_MODEL = os.environ.get("NOTEBOOKLM_OFFICIAL_VIDEO_MODEL", "veo-3.0-generate-001")


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

        # In-memory job table: notebook_id -> list of artifact dicts (official
        # ops are effectively synchronous, but poll_studio_status still works).
        self._jobs: dict[str, list[dict[str, Any]]] = {}

    # ---- supported subset (implemented in phases 2-3) ----

    def get_notebook_sources_with_types(self, notebook_id: str) -> list[dict[str, Any]]:
        # Official backend has no NotebookLM-side sources. Return a single virtual
        # source so the studio service's source-resolution check passes; the actual
        # content is supplied via focus_prompt/sources_text. (Phase 3 adds a real
        # per-notebook source registry for grounded report/query.)
        return [{"id": f"official:{notebook_id}", "type": "virtual"}]

    def create_audio_overview(
        self,
        notebook_id: str,
        *,
        source_ids: list[str] | None = None,
        format_code: int = 0,
        length_code: int = 0,
        language: str = "en",
        focus_prompt: str = "",
        sources_text: str = "",
        target_minutes: float = 2.5,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a multi-speaker TTS podcast and upload it to GCS.

        ``focus_prompt`` carries the topic/direction; ``sources_text`` (when
        provided by the pipeline) grounds the script. Returns a CreateResult-
        shaped dict; the finished artifact is also recorded for poll_studio_status.
        """
        from . import official_audio

        topic = focus_prompt.strip() or "An overview of the provided sources."
        result = official_audio.create_podcast(
            self._client,
            topic=topic,
            sources_text=sources_text,
            target_minutes=target_minutes,
            language=language,
        )
        artifact = {
            "artifact_id": result.artifact_id,
            "type": "audio",
            "title": "Audio Overview (official)",
            "status": result.status,
            "audio_url": result.audio_url,
            "gcs_uri": result.gcs_uri,
            "duration_seconds": result.duration_seconds,
        }
        self._jobs.setdefault(notebook_id, []).append(artifact)
        return {
            "artifact_id": result.artifact_id,
            "status": result.status,
            "audio_url": result.audio_url,
        }

    def create_report(
        self,
        notebook_id: str,
        *,
        source_ids: list[str] | None = None,
        report_format: str = "Briefing Doc",
        custom_prompt: str = "",
        language: str = "en",
        sources_text: str = "",
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a grounded markdown report on the google-genai TEXT model.

        ``custom_prompt`` carries the topic/direction; ``sources_text`` (when
        provided by the pipeline) grounds the report. Returns a CreateResult-
        shaped dict; the finished artifact is also recorded for poll_studio_status.
        """
        from . import official_report

        topic = custom_prompt.strip() or "A report synthesizing the provided sources."
        result = official_report.create_report(
            self._client,
            topic=topic,
            sources_text=sources_text,
            report_format=report_format,
            language=language,
        )
        artifact = {
            "artifact_id": result["artifact_id"],
            "type": "report",
            "title": "Report (official)",
            "status": result["status"],
            "report_content": result["report_content"],
            "report_format": result["report_format"],
        }
        self._jobs.setdefault(notebook_id, []).append(artifact)
        return {
            "artifact_id": result["artifact_id"],
            "status": result["status"],
            "report_content": result["report_content"],
        }

    def create_video_overview(
        self,
        notebook_id: str,
        *,
        source_ids: list[str] | None = None,
        format_code: int = 0,
        visual_style_code: int | None = None,
        visual_style_prompt: str = "",
        language: str = "en",
        focus_prompt: str = "",
        duration_seconds: int | None = None,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Generate a Veo video and upload it to GCS.

        ``focus_prompt`` carries the scene/direction; ``visual_style_prompt`` the
        style. Veo is cost-heavy — duration defaults are kept short (env-tunable).
        Returns a CreateResult-shaped dict; the artifact is recorded for polling.
        """
        from . import official_video

        prompt = focus_prompt.strip() or "A short cinematic clip illustrating the topic."
        kw: dict[str, Any] = {"prompt": prompt, "style_prompt": visual_style_prompt}
        if duration_seconds is not None:
            kw["duration_seconds"] = duration_seconds
        result = official_video.create_video(self._client, **kw)
        artifact = {
            "artifact_id": result["artifact_id"],
            "type": "video",
            "title": "Video Overview (official)",
            "status": result["status"],
            "video_url": result["video_url"],
            "gcs_uri": result["gcs_uri"],
            "duration_seconds": result["duration_seconds"],
        }
        self._jobs.setdefault(notebook_id, []).append(artifact)
        return {
            "artifact_id": result["artifact_id"],
            "status": result["status"],
            "video_url": result["video_url"],
        }

    def poll_studio_status(self, notebook_id: str) -> list[dict[str, Any]]:
        """Return artifacts produced for this notebook_id (official ops finish synchronously)."""
        return list(self._jobs.get(notebook_id, []))

    # ---- explicitly unsupported (NotebookLM-only) ----

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
