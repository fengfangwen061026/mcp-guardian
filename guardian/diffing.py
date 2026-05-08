from __future__ import annotations

import difflib
from pathlib import Path


def unified_diff(path: str | Path, old: str, new: str) -> str:
    name = str(path)
    return "".join(
        difflib.unified_diff(
            old.splitlines(keepends=True),
            new.splitlines(keepends=True),
            fromfile=f"{name} (current)",
            tofile=f"{name} (proposed)",
        )
    )
