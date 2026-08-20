"""Anchored `.env` loading.

`load_dotenv()` with no arguments resolves relative to the calling file (or the
CWD), which makes `.env` discovery depend on how the process was launched — fine
for `python main.py` from the repo root, unreliable for an installed console
script whose MCP client may not set `cwd` at all.

`load_env()` looks in both plausible places and never overrides a variable that
is already set, so the `env` map an MCP client passes to the subprocess always
wins over any file on disk.
"""

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

# Same idiom as internal/db/connection.py: walk up from this file to the
# checkout root, so a dev/editable install finds its .env regardless of CWD.
_PACKAGE_ROOT = Path(__file__).resolve().parents[1]

_loaded = False


def load_env() -> None:
    """Load `.env` once per process. Idempotent and safe to call from anywhere."""
    global _loaded
    if _loaded:
        return
    _loaded = True

    # 1. Walk up from the CWD — covers an MCP client that sets `cwd` to a checkout.
    cwd_env = find_dotenv(usecwd=True)
    if cwd_env:
        load_dotenv(cwd_env, override=False)

    # 2. The checkout root next to this package — covers an editable install
    #    launched from an unrelated directory.
    package_env = _PACKAGE_ROOT / ".env"
    if package_env.is_file() and os.fspath(package_env) != cwd_env:
        load_dotenv(package_env, override=False)
