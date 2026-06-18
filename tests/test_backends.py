"""Unit tests for the hybrid backend layer (mocked — NO live API calls).

Everything here runs offline:
- factory.get_backend_name env honoring
- errors.UnsupportedOnBackend message/attrs
- factory._FallbackProxy fallback routing (fakes, no real backends)
- official_audio.pcm_to_wav WAV correctness (parsed with the stdlib `wave` module)
- OfficialBackend.* UnsupportedOnBackend artifacts WITHOUT google-genai installed

For the OfficialBackend tests we use ``object.__new__(OfficialBackend)`` to build an
instance WITHOUT running ``__init__`` (which would import google-genai and resolve
real creds). The unsupported-artifact methods only ``raise UnsupportedOnBackend`` and
never touch ``self._client``, so a credential-free instance exercises them faithfully.
"""

from __future__ import annotations

import io
import wave

import pytest

from notebooklm_tools.backends import factory, official_audio
from notebooklm_tools.backends.errors import BackendError, UnsupportedOnBackend
from notebooklm_tools.backends.official import OfficialBackend


# ---------- factory.get_backend_name ----------


def test_get_backend_name_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NOTEBOOKLM_BACKEND", raising=False)
    assert factory.get_backend_name() == "notebooklm"


def test_get_backend_name_official(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTEBOOKLM_BACKEND", "official")
    assert factory.get_backend_name() == "official"


def test_get_backend_name_official_case_and_whitespace(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTEBOOKLM_BACKEND", "  OFFICIAL  ")
    assert factory.get_backend_name() == "official"


def test_get_backend_name_invalid_falls_back_to_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NOTEBOOKLM_BACKEND", "bogus")
    assert factory.get_backend_name() == "notebooklm"


# ---------- errors.UnsupportedOnBackend ----------


def test_unsupported_on_backend_attrs_and_message() -> None:
    err = UnsupportedOnBackend("quiz", "official")
    assert err.operation == "quiz"
    assert err.backend == "official"
    assert isinstance(err, BackendError)
    msg = str(err)
    assert "quiz" in msg
    assert "official" in msg
    assert "NOTEBOOKLM_OFFICIAL_FALLBACK" in msg


# ---------- factory._FallbackProxy ----------


class _Primary:
    """Fake primary backend: one method works, one is unsupported."""

    def supported(self, value: str) -> str:
        return f"primary:{value}"

    def needs_fallback(self, value: str) -> str:
        raise UnsupportedOnBackend("needs_fallback", "primary")

    plain_attr = "primary-attr"


class _Secondary:
    """Fake secondary backend used only on fallback."""

    def __init__(self) -> None:
        self.built = True

    def needs_fallback(self, value: str) -> str:
        return f"secondary:{value}"

    def supported(self, value: str) -> str:  # pragma: no cover - should not be reached
        return f"secondary-supported:{value}"


def test_fallback_proxy_primary_handles_supported() -> None:
    built = {"count": 0}

    def secondary_factory() -> _Secondary:
        built["count"] += 1
        return _Secondary()

    proxy = factory._FallbackProxy(_Primary(), secondary_factory)
    assert proxy.supported("x") == "primary:x"
    # Secondary must not be built when primary succeeds.
    assert built["count"] == 0


def test_fallback_proxy_routes_unsupported_to_secondary() -> None:
    built = {"count": 0}

    def secondary_factory() -> _Secondary:
        built["count"] += 1
        return _Secondary()

    proxy = factory._FallbackProxy(_Primary(), secondary_factory)
    assert proxy.needs_fallback("y") == "secondary:y"
    # Secondary built exactly once (lazily, on first fallback).
    assert built["count"] == 1
    # A second fallback reuses the cached secondary.
    assert proxy.needs_fallback("z") == "secondary:z"
    assert built["count"] == 1


def test_fallback_proxy_passes_through_non_callable_attr() -> None:
    proxy = factory._FallbackProxy(_Primary(), _Secondary)
    assert proxy.plain_attr == "primary-attr"


# ---------- official_audio.pcm_to_wav ----------


def test_pcm_to_wav_produces_valid_wav() -> None:
    # 4 frames of 16-bit mono PCM (8 bytes).
    pcm = b"\x00\x01\x02\x03\x04\x05\x06\x07"
    wav_bytes = official_audio.pcm_to_wav(pcm, "audio/L16;codec=pcm;rate=24000")

    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert w.getframerate() == 24000
        assert w.getnchannels() == 1
        assert w.getsampwidth() == 2
        # 8 bytes / (1 channel * 2 bytes) == 4 frames.
        assert w.getnframes() == 4
        assert w.readframes(4) == pcm


def test_pcm_to_wav_defaults_rate_when_absent() -> None:
    wav_bytes = official_audio.pcm_to_wav(b"\x00\x00", "audio/L16;codec=pcm")
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        assert w.getframerate() == 24000


# ---------- OfficialBackend unsupported artifacts (no google-genai needed) ----------


def _credless_backend() -> OfficialBackend:
    """Build an OfficialBackend WITHOUT running __init__.

    __init__ imports google-genai and resolves real creds. The unsupported-artifact
    methods only raise UnsupportedOnBackend and never read self._client, so bypassing
    __init__ with object.__new__ lets us test them offline with no SDK / creds.
    """
    return object.__new__(OfficialBackend)  # type: ignore[no-any-return]


@pytest.mark.parametrize(
    ("method", "expected_op"),
    [
        ("create_video_overview", "video"),
        ("create_infographic", "infographic"),
        ("create_slide_deck", "slide_deck"),
        ("generate_mind_map", "mind_map"),
        ("create_quiz", "quiz"),
        ("create_flashcards", "flashcards"),
        ("create_data_table", "data_table"),
    ],
)
def test_official_backend_unsupported_artifacts_raise(method: str, expected_op: str) -> None:
    backend = _credless_backend()
    with pytest.raises(UnsupportedOnBackend) as exc_info:
        getattr(backend, method)("notebook-1")
    assert exc_info.value.operation == expected_op
    assert exc_info.value.backend == "official"


# ---------- OfficialBackend.create_report (mocked genai client) ----------


class _FakeGenAIResponse:
    def __init__(self, text: str) -> None:
        self.text = text


class _FakeModels:
    def __init__(self, text: str) -> None:
        self._text = text
        self.calls: list[dict] = []

    def generate_content(self, *, model, contents, config=None):  # noqa: ANN001
        self.calls.append({"model": model, "contents": contents})
        return _FakeGenAIResponse(self._text)


class _FakeClient:
    def __init__(self, text: str) -> None:
        self.models = _FakeModels(text)


def test_official_backend_create_report_grounded(monkeypatch: pytest.MonkeyPatch) -> None:
    # Stub google.genai.types so official_report's local import works without the SDK.
    import sys
    import types as _pytypes

    fake_genai = _pytypes.ModuleType("google.genai")

    class _Cfg:
        def __init__(self, **kw):  # noqa: ANN003
            self.kw = kw

    fake_types = _pytypes.SimpleNamespace(GenerateContentConfig=_Cfg)
    fake_genai.types = fake_types  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "google.genai", fake_genai)

    backend = _credless_backend()
    backend._client = _FakeClient("# Title\n\nGrounded body.")  # type: ignore[attr-defined]
    backend._jobs = {}  # type: ignore[attr-defined]

    result = backend.create_report(
        "nb-1",
        custom_prompt="Summarize the sources",
        sources_text="The sky is blue.",
        report_format="Briefing Doc",
    )

    assert result["artifact_id"]
    assert result["status"] == "completed"
    assert "Grounded body" in result["report_content"]
    # Artifact recorded for polling.
    jobs = backend._jobs["nb-1"]  # type: ignore[attr-defined]
    assert len(jobs) == 1
    assert jobs[0]["type"] == "report"
    # sources_text was injected into the grounded prompt.
    sent = backend._client.models.calls[0]["contents"]  # type: ignore[attr-defined]
    assert "The sky is blue." in sent
    assert "ONLY" in sent
