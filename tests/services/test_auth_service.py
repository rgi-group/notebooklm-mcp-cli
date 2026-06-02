"""Tests for the services.auth re-export shim.

The shim exists to satisfy the layering rule (cli/ and mcp/ must not import
from core/); the real behavior lives in core.auth. These tests pin the
re-export contract so the shim does not silently drift.
"""

from notebooklm_tools.core import auth as core_auth
from notebooklm_tools.services import auth as services_auth


def test_shim_reexports_expected_auth_symbols():
    """The shim exposes the full set of auth symbols needed by cli/mcp:
    check_auth (function), the four data/auth helpers (load_cached_tokens,
    save_tokens_to_cache, get_cache_path, validate_cookies), and the two
    class symbols (AuthTokens, AuthManager).
    """
    assert sorted(services_auth.__all__) == sorted(
        [
            "AuthManager",
            "AuthTokens",
            "check_auth",
            "get_cache_path",
            "load_cached_tokens",
            "save_tokens_to_cache",
            "validate_cookies",
        ]
    )


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


def test_shim_load_cached_tokens_forwards_to_core(monkeypatch):
    """`load_cached_tokens` wrapper must call the core implementation and
    return its result.
    """
    sentinel = object()

    def _fake_load():
        return sentinel

    monkeypatch.setattr(core_auth, "load_cached_tokens", _fake_load, raising=True)
    assert services_auth.load_cached_tokens() is sentinel


def test_shim_save_tokens_to_cache_forwards_kwargs(monkeypatch):
    """`save_tokens_to_cache` wrapper must forward (tokens, silent=...) to
    the core implementation.
    """
    captured = {}

    def _fake_save(tokens, silent=False):
        captured["tokens"] = tokens
        captured["silent"] = silent

    sentinel_tokens = object()
    monkeypatch.setattr(core_auth, "save_tokens_to_cache", _fake_save, raising=True)
    services_auth.save_tokens_to_cache(sentinel_tokens, silent=True)
    assert captured == {"tokens": sentinel_tokens, "silent": True}


def test_shim_validate_cookies_forwards_to_core(monkeypatch):
    """`validate_cookies` wrapper must forward the cookies dict and return
    the core result.
    """
    captured = {}

    def _fake_validate(cookies):
        captured["cookies"] = cookies
        return "ok"

    monkeypatch.setattr(core_auth, "validate_cookies", _fake_validate, raising=True)
    result = services_auth.validate_cookies({"SID": "sid"})
    assert result == "ok"
    assert captured == {"cookies": {"SID": "sid"}}


def test_shim_auth_manager_resolves_to_current_core_class(monkeypatch):
    """`services.auth.AuthManager` must resolve to the CURRENT
    `core.auth.AuthManager`, not a snapshot taken at import time. Verified
    by patching core.auth.AuthManager with a sentinel class and confirming
    the shim's PEP 562 `__getattr__` returns the patched class on access.
    """
    sentinel_class = type("SentinelAuthManager", (), {})

    monkeypatch.setattr(core_auth, "AuthManager", sentinel_class, raising=True)
    assert services_auth.AuthManager is sentinel_class


def test_shim_auth_tokens_resolves_to_current_core_class(monkeypatch):
    """`services.auth.AuthTokens` must resolve to the current
    `core.auth.AuthTokens` on every access (no caching).
    """
    sentinel_class = type("SentinelAuthTokens", (), {})

    monkeypatch.setattr(core_auth, "AuthTokens", sentinel_class, raising=True)
    assert services_auth.AuthTokens is sentinel_class


def test_shim_class_resolution_works_through_from_import(monkeypatch):
    """The pattern `from notebooklm_tools.services.auth import AuthManager`
    inside a function body must pick up a monkeypatched core.auth.AuthManager,
    just like the inline import pattern. This pins the contract that
    downstream code (cli/main.py, etc.) relies on.
    """
    sentinel_class = type("FromImportSentinel", (), {})

    monkeypatch.setattr(core_auth, "AuthManager", sentinel_class, raising=True)
    # Re-execute the import statement the same way cli code does.
    local_namespace = {}
    exec("from notebooklm_tools.services.auth import AuthManager", local_namespace)
    assert local_namespace["AuthManager"] is sentinel_class


def test_shim_class_resolution_does_not_cache_across_patches(monkeypatch):
    """Caching PEP 562 lookups in module globals would poison the shim
    for any caller that imports early (e.g. cli/utils.py:13) and then
    runs a test that monkeypatches core.auth.AuthManager. This test
    pins the no-cache contract by patching twice and confirming both
    patches are observed.
    """
    first_class = type("FirstSentinel", (), {})
    second_class = type("SecondSentinel", (), {})

    monkeypatch.setattr(core_auth, "AuthManager", first_class, raising=True)
    assert services_auth.AuthManager is first_class
    monkeypatch.setattr(core_auth, "AuthManager", second_class, raising=True)
    assert services_auth.AuthManager is second_class, (
        "PEP 562 lookup must re-resolve on every access; a cache would "
        "leak the first patched class into the second access."
    )
