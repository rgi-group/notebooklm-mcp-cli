"""Official backend — audio (multi-speaker TTS podcast) on Vertex AI.

Pipeline: topic/sources -> grounded 2-host dialogue script (text model) ->
multi-speaker TTS (gemini Flash TTS) -> PCM -> WAV -> upload to GCS -> return url.

This is the piece that replaces the manual NotebookLM Audio-Overview export in the
Bingo content pipeline. Everything runs through the google-genai SDK against Vertex
(project/location/ADC from ~/.notebooklm-official.env); GCS upload uses ADC too.
"""

from __future__ import annotations

import io
import os
import re
import uuid
import wave
from dataclasses import dataclass
from typing import Any

# Newest Flash models preferred; both verified on Vertex (us-central1) for b1ngo-463301.
TTS_MODEL = os.environ.get("NOTEBOOKLM_OFFICIAL_TTS_MODEL", "gemini-2.5-flash-preview-tts")
TEXT_MODEL = os.environ.get("NOTEBOOKLM_OFFICIAL_TEXT_MODEL", "gemini-2.5-flash")
GCS_BUCKET = os.environ.get("NOTEBOOKLM_OFFICIAL_GCS_BUCKET", "bingo-codes-blog")
GCS_PREFIX = os.environ.get("NOTEBOOKLM_OFFICIAL_GCS_PREFIX", "official-podcasts")

# Two distinct prebuilt voices for the host A/B split.
VOICE_A = os.environ.get("NOTEBOOKLM_OFFICIAL_VOICE_A", "Kore")
VOICE_B = os.environ.get("NOTEBOOKLM_OFFICIAL_VOICE_B", "Puck")
SPEAKER_A = "Host A"
SPEAKER_B = "Host B"


@dataclass
class PodcastResult:
    artifact_id: str
    status: str
    audio_url: str
    gcs_uri: str
    duration_seconds: int
    script: str


# ---------- PCM -> WAV ----------

_RATE_RE = re.compile(r"rate=(\d+)")


def pcm_to_wav(pcm: bytes, mime_type: str, *, channels: int = 1, sample_width: int = 2) -> bytes:
    """Wrap raw L16 PCM (as returned by Gemini TTS) in a WAV container."""
    m = _RATE_RE.search(mime_type or "")
    rate = int(m.group(1)) if m else 24000
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(sample_width)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _wav_duration_seconds(wav_bytes: bytes) -> int:
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        frames = w.getnframes()
        rate = w.getframerate() or 24000
    return round(frames / rate) if rate else 0


# ---------- script ----------


def generate_dialogue_script(
    client: Any,
    *,
    topic: str,
    sources_text: str = "",
    target_minutes: float = 2.0,
    language: str = "en",
) -> str:
    """Generate a grounded two-host podcast script.

    If sources_text is provided the script is grounded ONLY on it (NotebookLM-style,
    no hallucinated facts). Output uses 'Host A:' / 'Host B:' line labels.
    """
    from google.genai import types

    grounding = (
        f"Ground the conversation ONLY in these sources; do not invent facts:\n\n{sources_text}\n\n"
        if sources_text.strip()
        else ""
    )
    prompt = (
        f"Write a natural, engaging two-host podcast script in {language}.\n"
        f"Hosts are '{SPEAKER_A}' and '{SPEAKER_B}'. Roughly {target_minutes:.0f} minute(s).\n"
        f"{grounding}"
        f"Topic / direction: {topic}\n\n"
        f"Rules: every line starts with '{SPEAKER_A}:' or '{SPEAKER_B}:'. "
        f"Conversational, no stage directions, no markdown, alternate speakers."
    )
    resp = client.models.generate_content(
        model=TEXT_MODEL,
        contents=prompt,
        config=types.GenerateContentConfig(temperature=0.8),
    )
    script = (resp.text or "").strip()
    if SPEAKER_A not in script and SPEAKER_B not in script:
        # Fallback: force a minimal labeled exchange so TTS multi-speaker still works.
        script = f"{SPEAKER_A}: {script}"
    return script


# ---------- TTS ----------


def synthesize(client: Any, script: str) -> tuple[bytes, str]:
    """Multi-speaker TTS the labeled script. Returns (pcm_bytes, mime_type)."""
    from google.genai import types

    resp = client.models.generate_content(
        model=TTS_MODEL,
        contents=f"TTS the following two-host conversation:\n\n{script}",
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=[
                        types.SpeakerVoiceConfig(
                            speaker=SPEAKER_A,
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_A)
                            ),
                        ),
                        types.SpeakerVoiceConfig(
                            speaker=SPEAKER_B,
                            voice_config=types.VoiceConfig(
                                prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=VOICE_B)
                            ),
                        ),
                    ]
                )
            ),
        ),
    )
    part = resp.candidates[0].content.parts[0].inline_data
    return part.data, part.mime_type


# ---------- GCS ----------


def upload_to_gcs(
    data: bytes, blob_name: str, *, content_type: str = "audio/wav"
) -> tuple[str, str]:
    """Upload bytes to GCS via ADC. Returns (gs_uri, https_url).

    Shared by audio (WAV) and video (MP4) — pass the appropriate content_type.
    """
    from google.cloud import storage

    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    client = storage.Client(project=project)
    bucket = client.bucket(GCS_BUCKET)
    blob = bucket.blob(blob_name)
    blob.upload_from_string(data, content_type=content_type)
    gs_uri = f"gs://{GCS_BUCKET}/{blob_name}"
    https_url = f"https://storage.googleapis.com/{GCS_BUCKET}/{blob_name}"
    return gs_uri, https_url


# ---------- orchestration ----------


def create_podcast(
    client: Any,
    *,
    topic: str,
    sources_text: str = "",
    target_minutes: float = 2.0,
    language: str = "en",
    script: str | None = None,
) -> PodcastResult:
    """End-to-end: script -> TTS -> WAV -> GCS. Returns PodcastResult."""
    if script is None:
        script = generate_dialogue_script(
            client,
            topic=topic,
            sources_text=sources_text,
            target_minutes=target_minutes,
            language=language,
        )
    pcm, mime = synthesize(client, script)
    wav = pcm_to_wav(pcm, mime)
    artifact_id = uuid.uuid4().hex
    blob_name = f"{GCS_PREFIX}/{artifact_id}.wav"
    gs_uri, https_url = upload_to_gcs(wav, blob_name)
    return PodcastResult(
        artifact_id=artifact_id,
        status="completed",
        audio_url=https_url,
        gcs_uri=gs_uri,
        duration_seconds=_wav_duration_seconds(wav),
        script=script,
    )
