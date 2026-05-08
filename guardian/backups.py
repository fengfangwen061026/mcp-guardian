from __future__ import annotations

import shutil
import time
from pathlib import Path


def create_backup(path: str | Path) -> str:
    source = Path(path).expanduser().resolve()
    backup_path = source.with_name(f".{source.name}.{time.strftime('%Y%m%d%H%M%S')}.{time.time_ns()}.bak")
    shutil.copy2(source, backup_path)
    return str(backup_path)
