"""Java / Kotlin extractor (structural regex, stdlib-only)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

RE_PACKAGE = re.compile(r"^[\t ]*package\s+([\w.]+)\s*;?/?$", re.M)
RE_IMPORT = re.compile(r"^[\t ]*import\s+(?:static\s+)?([\w.*]+)\s*;?", re.M)
RE_TYPE_DECL = re.compile(
    r"^[\t ]*(?:[\w$.]+\s+)+(?:class|interface|enum|record|object)\s+(\w+)"
    r"|^[\t ]*(?:class|interface|enum|record|object)\s+(\w+)",
    re.M,
)
RE_TYPE_HEADER = re.compile(
    r"^(?:(?:[\w$.]+\s+)*)(class|interface|enum|record|object)\s+(\w+)([^\n{]*)",
    re.M,
)
RE_KOTLIN_FUNC = re.compile(
    r"^[\t ]*(?:@\w+(?:\([^)]*\))?\s+)*"
    r"(?:(?:public|private|protected|internal|suspend|inline|override|final|open|operator)\s+)*"
    r"fun\s+(?:<[^>]*>\s*)?([A-Za-z_][\w]*)",
    re.M,
)
RE_JAVA_METHOD = re.compile(
    r"^[\t ]*(?:@\w+(?:\([^)]*\))?\s+)*"
    r"(?:(?:public|private|protected)\s+)?"
    r"(?:(?:static|final|abstract|synchronized|default|native)\s+)*"
    r"(?:[\w$.<>]+(?:<[^>(){};]*>)?)\s+([A-Za-z_][\w]*)\s*\(([^;)]*)\)\s*(?:throws\s+[\w,. ]+)?\s*(?:\{|;)",
    re.M,
)

SKIP_METHODS = {
    "if", "for", "while", "switch", "catch", "return", "new", "super",
    "this", "void", "static", "getter", "setter",
}


def file_id(rel: str) -> str:
    return f"file::{rel}"


def extract_jvm(path: Path, rel: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4_000_000]
    except OSError:
        return {"nodes": [], "edges": []}

    f_id = file_id(rel)
    nodes: list[dict[str, Any]] = [
        {"id": f_id, "label": Path(path).name, "file_type": "code", "source_file": rel}
    ]
    edges: list[dict[str, Any]] = []

    packages = RE_PACKAGE.findall(text)
    if packages:
        nodes.append({"id": f"package::{packages[0]}", "label": packages[0],
                      "file_type": "code", "source_file": rel})
        edges.append({"source": f_id, "target": f"package::{packages[0]}", "relation": "belongs_to",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    imports: set[str] = set(RE_IMPORT.findall(text))
    for imp in sorted(imports):
        edges.append({"source": f_id, "target": f"module::{imp}", "relation": "imports",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---- type declarations ---------------------------------------------- #
    type_names: set[str] = set()
    for m in RE_TYPE_DECL.finditer(text):
        name = m.group(1) or m.group(2) or ""
        header = RE_TYPE_HEADER.match(text[m.start():])
        if header is None:
            if not name or name in type_names:
                continue
            tail = ""
        else:
            _, hname, tail = header.group(1), header.group(2), header.group(3) or ""
            name = name or hname
        if not name or name in type_names:
            continue
        type_names.add(name)
        tid = f"{rel}::{name}"
        kind = (header.group(1) if header else re.search(r"(class|interface|enum|record|object)", text[m.start()]) .group(1))  # noqa: E501
        nodes.append({"id": tid, "label": name, "file_type": "code", "source_file": rel,
                      "source_location": f"L{text.count(chr(10), 0, m.start()) + 1}", "kind": kind})
        edges.append({"source": f_id, "target": tid, "relation": "contains",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})
        _edges_from_header_tail(edges, tid, tail, rel)

    # ---- methods --------------------------------------------------------- #
    methods: set[str] = set()
    for regex in (RE_KOTLIN_FUNC, RE_JAVA_METHOD):
        for m in regex.finditer(text):
            name = m.group(1)
            if name in methods or name in SKIP_METHODS or name in type_names:
                continue
            methods.add(name)
            mid = f"{rel}::{name}()"
            nodes.append({"id": mid, "label": f"{name}()", "file_type": "code", "source_file": rel,
                          "source_location": f"L{text.count(chr(10), 0, m.start()) + 1}", "kind": "method"})
            edges.append({"source": f_id, "target": mid, "relation": "contains",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for e in edges:
        k = (e["source"], e["target"], e["relation"])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return {"nodes": nodes, "edges": out}


def _edges_from_header_tail(
    edges: list[dict[str, Any]], tid: str, tail: str, rel: str
) -> None:
    pieces = (p.strip() for p in tail.split("implements"))
    for idx, piece in enumerate(pieces):
        for sep in ("extends", ":", "super"):
            if sep in piece and piece.index(sep) >= 0:
                piece = piece.split(sep, 1)[1]
        for candidate in (c.strip().split(".")[-1] for c in piece.split(",")):
            if candidate and re.fullmatch(r"[A-Za-z_][\w]*", candidate):
                relation = "implements" if idx > 0 else "inherits"
                edges.append({"source": tid, "target": f"class::{candidate}", "relation": relation,
                              "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})
