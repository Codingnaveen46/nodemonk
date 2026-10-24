"""Markdown / text extractor - headings, wiki-links, citations, code references."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

RE_HEADING = re.compile(r"^(#{1,4})\s+(.*)$", re.M)
RE_WIKI = re.compile(r"\[\[([^\[\]|]+?)(?:\|[^\[\]]+)?\]\]")
RE_MD_LINK = re.compile(r"\[[^\]]+\]\(([^)\s]+)\)")
RE_URL = re.compile(r"\bhttps?://[^\s)>\]]+", re.I)
RE_REF = re.compile(r"\[?`?([\w./-]+\.[A-Za-z]{1,8})(?::(\d+))?`?\]?")
RE_CITE = re.compile(r"\[@([\w\-:./]+)|\(([\w-]+ et al\.? \d{4})\)")


def file_id(rel: str) -> str:
    return f"file::{rel}"


def slugify(text: str) -> str:
    s = re.sub(r"[^\w\s-]", "", text.lower()).strip()
    return re.sub(r"[\s_]+", "-", s)[:80] or "section"


def extract_markdown(path: Path, rel: str, file_type: str = "document") -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:6_000_000]
    except OSError:
        return {"nodes": [], "edges": []}

    f_id = file_id(rel)
    title = Path(path).stem.replace("_", " ").strip() or Path(path).name
    nodes: list[dict[str, Any]] = [
        {"id": f_id, "label": title, "file_type": file_type, "source_file": rel}
    ]
    edges: list[dict[str, Any]] = []

    heading_stack: list[tuple[int, str]] = []  # (level, node_id)
    is_paper = file_type == "paper"

    for m in RE_HEADING.finditer(text):
        level, heading = len(m.group(1)), m.group(2).strip()
        if not heading or level > 3:
            continue
        if len(heading) > 120:
            heading = heading[:117] + "..."
        hid = f"{rel}::{slugify(heading)}"
        entry: dict[str, Any] = {
            "id": hid,
            "label": heading,
            "file_type": file_type,
            "source_file": rel,
            "source_location": f"L{text.count(chr(10), 0, m.start()) + 1}",
            "level": level,
        }
        nodes.append(entry)
        parent_id: str
        if heading_stack and level > heading_stack[-1][0]:
            parent_id = heading_stack[-1][1]
        else:
            while heading_stack and heading_stack[-1][0] >= level:
                heading_stack.pop()
            parent_id = heading_stack[-1][1] if heading_stack else f_id
        edges.append({"source": parent_id, "target": hid, "relation": "section",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})
        heading_stack.append((level, hid))

    for m in RE_WIKI.finditer(text):
        label = m.group(1).strip()
        if label:
            edges.append({"source": f_id, "target": f"symbol::{label}", "relation": "references",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    for m in RE_MD_LINK.finditer(text):
        link = m.group(1)
        if link.startswith(("#", "http", "mailto")):
            continue
        edges.append({"source": f_id, "target": f"file::{Path(link).as_posix()}",
                      "relation": "references", "confidence": "EXTRACTED",
                      "confidence_score": 1.0, "source_file": rel})
    for m in RE_URL.finditer(text):
        edges.append({"source": f_id, "target": f"url::{m.group(0)[:160]}", "relation": "links_to",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # code-file references: `src/foo.py:12`
    for m in RE_REF.finditer(text):
        ref_file, line_no = m.group(1), m.group(2)
        target_id = f"file::{ref_file}"
        nodes.append({"id": target_id, "label": Path(ref_file).name, "file_type": "code",
                      "source_file": ref_file, "stub": True})
        edge = {"source": f_id, "target": target_id, "relation": "references",
                "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel}
        if line_no:
            edge["source_location"] = f"{ref_file} L{line_no}"
        edges.append(edge)

    if is_paper:
        for m in RE_CITE.finditer(text):
            token = m.group(1) or m.group(2)
            if token:
                edges.append({"source": f_id, "target": f"cite::{token[:120]}",
                              "relation": "cites", "confidence": "EXTRACTED",
                              "confidence_score": 1.0, "source_file": rel})

    # stable semantic co-mention edges come from analyze.py (computed), not the reader

    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for e in edges:
        k = (e["source"], e["target"], e["relation"])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return {"nodes": nodes, "edges": out}
