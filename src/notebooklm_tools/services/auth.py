"""Service layer for auth.

Thin re-export of `check_auth` from core.auth so the MCP/CLI layers can
satisfy the layering rule (`cli/` and `mcp/` must not import from `core/`).
Business logic, validation, and error handling for auth live in
`notebooklm_tools.core.auth`; this module is intentionally a shim and
adds no behavior of its own.

The function wrapper below re-resolves `check_auth` on every call so tests
that monkeypatch `notebooklm_tools.core.auth.check_auth` continue to work
without also having to patch the re-exported binding. Without this, a
`from notebooklm_tools.core.auth import check_auth` at module scope would
capture the original function at import time and tests would silently fail.
"""

from notebooklm_tools.core import auth as _core_auth


def check_auth(*args, **kwargs):
    """Re-export of `notebooklm_tools.core.auth.check_auth`.

    Resolves the implementation lazily on each call so that monkeypatching
    `notebooklm_tools.core.auth.check_auth` (a common test pattern) is
    observed by callers of this shim.
    """
    return _core_auth.check_auth(*args, **kwargs)


__all__ = ["check_auth"]
