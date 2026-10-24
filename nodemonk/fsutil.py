"""Filesystem helpers: atomic writes, bounded reads."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path


def atomic_write(path: Path, text: str) -> None:
    """Write a file atomically: temp file + os.replace, crash-safe on re-run."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=".nm-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def read_text_limited(path: Path, max_bytes: int) -> tuple[str, bool]:
    """Read up to max_bytes. Returns (text, truncated)."""
    try:
        with open(path, "rb") as fh:
            blob = fh.read(max_bytes + 1)
    except OSError:
        return "", False
    truncated = len(blob) > max_bytes
    if truncated:
        blob = blob[:max_bytes]
    return blob.decode("utf-8", "replace"), truncated


@contextmanager
def chunk_reader(path: Path, chunk: int = 1 << 20):
    """Yield decoded text chunks without loading whole file (for hashing streams)."""
    fh = open(path, "rb")
    try:
        while True:
            blob = fh.read(chunk)
            if not blob:
                break
            yield blob.decode("utf-8", "replace")
    finally:
        fh.close()


def human_bytes(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"
