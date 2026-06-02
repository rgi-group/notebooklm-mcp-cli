"""Tests for the services.auth re-export shim.

The shim exists to satisfy the layering rule (cli/ and mcp/ must not import
from core/); the real behavior lives in core.auth. These tests pin the
re-export contract so the shim does not silently drift.
"""

from notebooklm_tools.core import auth as core_auth
from notebooklm_tools.services import auth as services_auth


def test_shim_reexports_only_check_auth():
    """The shim exposes only `check_auth` — no accidental kitchen-sink."""
    assert sorted(services_auth.__all__) == ["check_auth"]


def test_shim_check_auth_forwards_to_core_implementation(monkeypatch):
    """`services.auth.check_auth(...)` must delegate to
    `notebooklm_tools.core.auth.check_auth`. Verified by patching the core
    function and confirming the shim picks up the patch (i.e. it does not
    capture the original function at import time).
    """
    sentinel_result = object()

    def _fake_check_auth(*args, **kwargs):
        return sentinel_result

    monkeypatch.setattr(core_auth, "check_auth", _fake_check_auth, raising=True)
    # The wrapper resolves lazily on each call, so a patch to core.check_auth
    # is observed by the shim.
    assert services_auth.check_auth(live=True) is sentinel_result


def test_shim_check_auth_passes_args_and_kwargs_through(monkeypatch):
    """Args and kwargs must be forwarded unchanged to the core implementation."""
    captured = {}

    def _capturing_check_auth(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return "ok"

    monkeypatch.setattr(core_auth, "check_auth", _capturing_check_auth, raising=True)
    services_auth.check_auth("positional", live=True, timeout=5)
    assert captured["args"] == ("positional",)
    assert captured["kwargs"] == {"live": True, "timeout": 5}
