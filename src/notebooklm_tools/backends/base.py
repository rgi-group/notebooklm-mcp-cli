"""Backend protocol — the seam between the MCP/service layer and the engine.

The existing ``core.client.NotebookLMClient`` (unofficial NotebookLM web API) and
the new ``backends.official.OfficialBackend`` (google-genai SDK) both satisfy the
parts of this surface they support. Service functions in ``services/*`` accept any
object matching the methods they call, so the protocol is intentionally a
*structural* superset documented here rather than enforced by inheritance.

Only the **automatable subset** is required of the official backend:
- ``create_audio_overview`` (multi-speaker TTS podcast)
- ``create_report`` (grounded synthesis) / query
- ``poll_studio_status`` / ``get_notebook_sources_with_types``

Everything else (video*, infographic, slide_deck, mind_map, quiz, flashcards,
data_table) is NotebookLM-only; the official backend raises
``UnsupportedOnBackend`` for those. (*Veo video is an optional official add-on.)
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class StudioBackend(Protocol):
    """Minimal studio surface both backends expose for the automatable subset."""

    backend_name: str

    def get_notebook_sources_with_types(self, notebook_id: str) -> list[dict[str, Any]]:
        """Return [{'id': str, 'type': str, ...}] for the notebook's sources."""
        ...

    def create_audio_overview(
        self,
        notebook_id: str,
        *,
        source_ids: list[str],
        format_code: int,
        length_code: int,
        language: str,
        focus_prompt: str,
    ) -> dict[str, Any] | None:
        """Create an audio (podcast) artifact. Official backend → multi-speaker TTS."""
        ...

    def create_report(
        self,
        notebook_id: str,
        *,
        source_ids: list[str],
        report_format: str,
        custom_prompt: str,
        language: str,
    ) -> dict[str, Any] | None:
        """Create a grounded text report. Official backend → Files API + grounding."""
        ...

    def poll_studio_status(self, notebook_id: str) -> list[dict[str, Any]]:
        """Return raw artifact dicts for status polling."""
        ...
