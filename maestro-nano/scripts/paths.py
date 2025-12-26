from __future__ import annotations

import os
from pathlib import Path


def get_maestro_nano_root() -> Path:
    """Return the maestro-nano root directory.

    Resolution order:
    1) MAESTRO_NANO_ROOT environment variable (recommended)
    2) Auto-detect relative to this file: <maestro-nano>/scripts/paths.py -> <maestro-nano>

    Raises:
        ValueError: if MAESTRO_NANO_ROOT is set but does not exist.
    """

    env = os.getenv("MAESTRO_NANO_ROOT")
    if env:
        p = Path(env).expanduser()
        # Allow relative paths (resolve from CWD)
        p = p.resolve()
        if not p.exists() or not p.is_dir():
            raise ValueError(f"MAESTRO_NANO_ROOT points to a missing directory: {p}")
        return p

    # scripts/ -> maestro-nano/
    return Path(__file__).resolve().parent.parent


def get_repo_root() -> Path:
    """Return the repo root (parent of maestro-nano root)."""

    return get_maestro_nano_root().parent
