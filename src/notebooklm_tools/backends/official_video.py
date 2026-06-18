"""Official backend — video (Veo) on Vertex AI / google-genai.

Pipeline: prompt (+ optional style) -> Veo generate_videos (long-running op) ->
poll to completion -> video bytes -> upload to GCS -> return url. Mirrors the
working pattern already used in the Bingo pipeline's produce_episode.py.

Veo is COST-HEAVY (~$0.40-0.75/sec). Defaults keep clips short. Model/duration/
resolution are env-overridable.
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

from .official_audio import GCS_BUCKET, upload_to_gcs  # noqa: F401 (bucket re-exported)

VIDEO_MODEL = os.environ.get("NOTEBOOKLM_OFFICIAL_VIDEO_MODEL", "veo-3.1-generate-preview")
GCS_VIDEO_PREFIX = os.environ.get("NOTEBOOKLM_OFFICIAL_VIDEO_PREFIX", "official-videos")
DEFAULT_DURATION = int(os.environ.get("NOTEBOOKLM_OFFICIAL_VIDEO_SECONDS", "8"))
DEFAULT_ASPECT = os.environ.get("NOTEBOOKLM_OFFICIAL_VIDEO_ASPECT", "16:9")
DEFAULT_RESOLUTION = os.environ.get("NOTEBOOKLM_OFFICIAL_VIDEO_RESOLUTION", "1080p")
POLL_INTERVAL = float(os.environ.get("NOTEBOOKLM_OFFICIAL_VIDEO_POLL", "15"))
POLL_TIMEOUT = float(os.environ.get("NOTEBOOKLM_OFFICIAL_VIDEO_TIMEOUT", "600"))


def _extract_video_bytes(client: Any, generated_video: Any) -> bytes:
    """Get the rendered MP4 bytes from a Veo result (bytes inline, or download uri)."""
    data = getattr(generated_video, "video_bytes", None)
    if data:
        return data
    uri = getattr(generated_video, "uri", None)
    if not uri:
        raise RuntimeError("Veo returned no video_bytes and no uri.")
    # Vertex may return a GCS/HTTPS uri — fetch it with an ADC bearer token.
    import google.auth
    import requests
    from google.auth.transport.requests import Request as GAuthRequest

    creds, _ = google.auth.default()
    creds.refresh(GAuthRequest())
    resp = requests.get(uri, headers={"Authorization": f"Bearer {creds.token}"}, timeout=120)
    resp.raise_for_status()
    return resp.content


def create_video(
    client: Any,
    *,
    prompt: str,
    style_prompt: str = "",
    duration_seconds: int = DEFAULT_DURATION,
    aspect_ratio: str = DEFAULT_ASPECT,
    resolution: str = DEFAULT_RESOLUTION,
    model: str = VIDEO_MODEL,
) -> dict[str, Any]:
    """Generate a Veo clip and upload it to GCS. Returns a CreateResult-shaped dict."""
    from google.genai import types

    full_prompt = f"{prompt}\n\nVisual style: {style_prompt}" if style_prompt.strip() else prompt

    operation = client.models.generate_videos(
        model=model,
        prompt=full_prompt,
        config=types.GenerateVideosConfig(
            aspect_ratio=aspect_ratio,
            resolution=resolution,
            duration_seconds=duration_seconds,
        ),
    )

    deadline = time.monotonic() + POLL_TIMEOUT
    while not operation.done:
        if time.monotonic() > deadline:
            raise TimeoutError(
                f"Veo generation exceeded {POLL_TIMEOUT:.0f}s; operation still running."
            )
        time.sleep(POLL_INTERVAL)
        operation = client.operations.get(operation)

    generated = operation.result.generated_videos[0].video
    data = _extract_video_bytes(client, generated)

    artifact_id = uuid.uuid4().hex
    blob_name = f"{GCS_VIDEO_PREFIX}/{artifact_id}.mp4"
    gs_uri, https_url = upload_to_gcs(data, blob_name, content_type="video/mp4")
    return {
        "artifact_id": artifact_id,
        "status": "completed",
        "video_url": https_url,
        "gcs_uri": gs_uri,
        "duration_seconds": duration_seconds,
    }
