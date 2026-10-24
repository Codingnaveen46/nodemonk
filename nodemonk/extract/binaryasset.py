"""Binary / opaque asset nodes: images, media, pdfs (identity without decoding)."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def extract_binary(path: Path, rel: str, category: str) -> dict[str, Any]:
    means = {"image": "image", "media": "media", "paper": "paper"}.get(category, "document")
    try:
        stat = path.stat()
    except OSError:
        return {"nodes": [], "edges": []}
    blob_head = b""
    with open(path, "rb") as fh:
        blob_head = fh.read(4096)
    digest = hashlib.sha256(blob_head + str(stat.st_size).encode()).hexdigest()[:16]
    nid = f"asset::{rel}::{digest}"
    node = {
        "id": nid,
        "label": Path(path).name,
        "file_type": means,
        "source_file": rel,
        "size": stat.st_size,
    }
    return {"nodes": [node], "edges": []}
