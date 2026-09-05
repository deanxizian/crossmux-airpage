from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=path.parent, suffix=".tmp", delete=False
        ) as file:
            temporary = Path(file.name)
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def write_json(path: Path, value: object) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, allow_nan=False).encode())


def read_json(path: Path) -> object:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("state file exceeds 1 MiB")
    return json.loads(path.read_text(encoding="utf-8"))
