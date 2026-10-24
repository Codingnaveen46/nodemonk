"""nodemonk.watch - folder watcher with debounce (pure stdlib polling)."""

from __future__ import annotations

import hashlib
import os
import signal
import subprocess
import sys
import time
from pathlib import Path


def tree_fingerprint(root: Path, max_files: int = 0) -> str:
    """Cheap-but-complete fingerprint: sizes+mtimes of every file (no full hashes)."""
    h = hashlib.sha256()
    count = 0
    root = root.resolve()
    stack = [root]
    while stack:
        cur = stack.pop()
        try:
            with os.scandir(cur) as it:
                entries = list(it)
        except OSError:
            continue
        entries.sort(key=lambda e: e.name)
        for entry in entries:
            if entry.is_dir(follow_symlinks=False):
                from .detect import _skip_dir

                if not _skip_dir(entry.name):
                    stack.append(Path(entry.path))
                continue
            if entry.is_file(follow_symlinks=False):
                try:
                    st = entry.stat()
                except OSError:
                    continue
                h.update(entry.name.encode())
                h.update(str(st.st_mtime_ns).encode())
                h.update(str(st.st_size).encode())
                count += 1
                if max_files and count >= max_files:
                    return h.hexdigest()
    return h.hexdigest()


def watch(root: Path, debounce: float = 3.0, command: list[str] | None = None) -> None:  # pragma: no cover
    root = root.resolve()
    cmd = command or [
        sys.executable, "-m", "nodemonk.cli", "build", str(root), "--update",
    ]
    sig = tree_fingerprint(root)
    last_built_sig = sig
    last_change = time.monotonic()
    pending = False
    print(f"nodemonk::watch on {root} (debounce {debounce:.1f}s, ctrl-c to stop)")
    print(f"rebuild command: {' '.join(cmd)}")
    stop = {"flag": False}

    def on_term(_signum: int, _frame: object) -> None:  # noqa: ANN001
        stop["flag"] = True
        raise KeyboardInterrupt

    signal.signal(signal.SIGINT, on_term)
    while not stop["flag"]:
        time.sleep(0.5)
        try:
            current = tree_fingerprint(root)
        except OSError:
            continue
        if current != sig:
            sig = current
            last_change = time.monotonic()
            pending = True
        if pending and (time.monotonic() - last_change) >= debounce:
            print(f"\n[nodemonk::watch] change detected -> rebuilding")
            code = subprocess.call(cmd)
            if code == 0:
                last_built_sig = sig
            pending = False
            print("[nodemonk::watch] watching again")
    print("watch stopped")
