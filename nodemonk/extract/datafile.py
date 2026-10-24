"""Structured-data extractor: JSON (exact), YAML/TOML/CSV (top-level keys)."""

from __future__ import annotations

import csv
import json
import re
from pathlib import Path
from typing import Any

RE_TOML_KEY = re.compile(r"^\[([^\[\]]+)\]|^([A-Za-z_][\w\-.]*)\s*=", re.M)
RE_YAML_KEY = re.compile(r"^[\t ]*([A-Za-z_][\w\-.]*)\s*:", re.M)


def file_id(rel: str) -> str:
    return f"file::{rel}"


def extract_datafile(path: Path, rel: str, ext: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4_000_000]
    except OSError:
        return {"nodes": [], "edges": []}

    f_id = file_id(rel)
    label = Path(path).name
    nodes: list[dict[str, Any]] = [{"id": f_id, "label": label, "file_type": "data", "source_file": rel}]
    edges: list[dict[str, Any]] = []

    key_nodes: set[str] = set()

    def add_key(name: str) -> None:
        if not name or name in key_nodes:
            return
        key_nodes.add(name)
        kid = f"{rel}::{name}"
        nodes.append({"id": kid, "label": name, "file_type": "data", "source_file": rel, "kind": "key"})
        edges.append({"source": f_id, "target": kid, "relation": "contains",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    if ext in {".json", ".geojson", ".jsonc"}:
        try:
            doc = json.loads(text)
            if isinstance(doc, dict):
                for key in list(doc.keys())[:2000]:
                    add_key(str(key))
                # nested references like "$ref": "other.json"
                for m in re.finditer(r'"\$ref"\s*:\s*"([^"]+)"', text):
                    edges.append({"source": f_id, "target": f"file::{Path(m.group(1)).as_posix()}",
                                  "relation": "references", "confidence": "EXTRACTED",
                                  "confidence_score": 1.0, "source_file": rel})
        except (json.JSONDecodeError, ValueError):
            pass
    elif ext in {".toml"}:
        for m in RE_TOML_KEY.finditer(text):
            section, plain = m.group(1), m.group(2)
            add_key((section or plain).split(".")[-1])
    elif ext == ".csv":
        try:
            rows = list(csv.reader(text.splitlines()))[:5]
            if rows:
                for col in rows[0]:
                    add_key(str(col))
        except (csv.Error, ValueError):
            pass
    else:
        # YAML / INI / env / properties - top-level keys only (honest depth limit)
        for m in RE_YAML_KEY.findall(text) or []:
            add_key(m) if isinstance(m, str) else None
        for m in RE_YAML_KEY.finditer(text):
            indent = m.start() - (text.rfind("\n", 0, m.start()) + 1)
            if indent == 0:
                add_key(m.group(1))

    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for e in edges:
        k = (e["source"], e["target"], e["relation"])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return {"nodes": nodes, "edges": out}
