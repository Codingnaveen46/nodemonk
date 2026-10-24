"""Manifest persistence + incremental diffing for nodemonk --update."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

MANIFEST_NAME = ".manifest.json"


def save_manifest(out_dir: Path, files: dict[str, dict[str, Any]]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / MANIFEST_NAME
    path.write_text(json.dumps(files, indent=1), encoding="utf-8")
    return path


def load_manifest(out_dir: Path) -> dict[str, dict[str, Any]] | None:
    path = out_dir / MANIFEST_NAME
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def detect_incremental(root: Path, out_dir: Path) -> dict[str, Any]:
    """Compare current scan with the stored manifest.

    Returns {"new_files": {category: [rels]}, "changed": [rels], "new_total": int,
             "all_files": {category: [rels]}, "unchanged": count}
    """
    from .detect import detect

    result = detect(root)
    previous = load_manifest(out_dir) or {}
    current = result["files"]

    new_or_changed: dict[str, str] = {}
    for rel, info in current.items():
        old = previous.get(rel)
        if old is None or old.get("sha") != info["sha"]:
            new_or_changed[rel] = info["category"]

    unchanged = len(current) - len(new_or_changed)
    grouped: dict[str, list[str]] = {}
    for rel, cat in new_or_changed.items():
        grouped.setdefault(cat, []).append(rel)

    return {
        "all_files": result["categories"],
        "new_files": grouped,
        "new_total": len(new_or_changed),
        "unchanged": unchanged,
        "total_files": result["total_files"],
        "total_words": result["total_words"],
        "extraction": "code_only" if all(c == "code" for c in grouped.values()) and grouped else "mixed",
    }


def manifest_sig(files: dict[str, dict[str, Any]]) -> str:
    import hashlib

    h = hashlib.sha256()
    for rel in sorted(files):
        h.update(rel.encode())
        h.update(files[rel].get("sha", "").encode())
    return h.hexdigest()[:12]
