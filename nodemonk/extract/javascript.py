"""JavaScript / TypeScript extractor (regex-structural, stdlib-only).

Nodes: file, class, function, interface/type/enum (TS).
Edges: imports (file -> module), contains, inherits, implements, calls.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

KEYWORDS = {
    "if", "while", "for", "switch", "catch", "return", "typeof", "new",
    "function", "class", "super", "delete", "void", "await", "async",
    "throw", "else", "do", "case", "yield", "in", "of", "this", "with",
    "console", "require", "module", "exports", "window", "document",
    "Object", "Array", "String", "Number", "Boolean", "Promise", "Error",
    "Math", "JSON", "Date", "Map", "Set", "RegExp", "Symbol", "Proxy",
}

RE_IMPORT = re.compile(r"^[\t ]*import\b[^;]*?['\"]([^'\"]+)['\"]", re.M)
RE_IMPORT_EQ = re.compile(r"^[\t ]*import\s+(?:[\w*\s{},]+$)", re.M)
RE_REQUIRE = re.compile(r"\brequire\(\s*['\"]([^'\"]+)['\"]\s*\)", re.M)
RE_DYNAMIC = re.compile(r"\bimport\(\s*['\"]([^'\"]+)['\"]\s*\)", re.M)
RE_FUNCTION = re.compile(r"^[\t ]*(?:export\s+(?:default\s+)?)?(?:async\s+)?function\s*\*?\s+([A-Za-z_$][\w$]*)", re.M)
RE_CLASS = re.compile(
    r"^[\t ]*(?:export\s+(?:default\s+)?)?(?:abstract\s+)?class\s+([A-Za-z_$][\w$]*)"
    r"(?:\s+extends\s+([A-Za-z_$][\w$.]*))?(?:\s+implements\s+([\w$,.\s]+?))?(?=\s*\{)",
    re.M,
)
RE_TS_STRUCTS = re.compile(r"^[\t ]*(?:export\s+)?(?:interface|enum|namespace)\s+([A-Za-z_$][\w$]*)", re.M)
RE_ARROW_FN = re.compile(r"^[\t ]*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?\(", re.M)
RE_CALL = re.compile(r"(?:([A-Za-z_$][\w$]*)\s*\.)?([A-Za-z_$][\w$]*)\s*(?:<[^()<>]*>)?\(", re.S)


def file_id(rel: str) -> str:
    return f"file::{rel}"


def _dedupe(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for e in items:
        key = (e["source"], e["target"], e["relation"])
        if key in seen:
            continue
        seen.add(key)
        out.append(e)
    return out


def _line_at(text: str, pos: int) -> int:
    return text.count("\n", 0, pos) + 1


def extract_js(path: Path, rel: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4_000_000]
    except OSError:
        return {"nodes": [], "edges": []}

    f_id = file_id(rel)
    nodes: list[dict[str, Any]] = [
        {"id": f_id, "label": Path(path).name, "file_type": "code", "source_file": rel}
    ]
    edges: list[dict[str, Any]] = []

    # ---------------- imports ------------------------------------------ #
    import_sources: list[str] = []
    import_sources.extend(m.group(1) for m in RE_IMPORT.finditer(text))
    import_sources.extend(m.group(1) for m in RE_REQUIRE.finditer(text))
    import_sources.extend(m.group(1) for m in RE_DYNAMIC.finditer(text))
    import_sources.extend(m.group(1) for m in RE_IMPORT_EQ.finditer(text))
    for src in sorted(set(import_sources)):
        edges.append({"source": f_id, "target": f"module::{src}", "relation": "imports",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---------------- classes ------------------------------------------ #
    class_names: set[str] = set()
    for m in RE_CLASS.finditer(text):
        name, parent, impls = m.group(1), m.group(2), m.group(3)
        if name in class_names:
            continue
        class_names.add(name)
        cid = f"{rel}::{name}"
        nodes.append({"id": cid, "label": name, "file_type": "code", "source_file": rel,
                      "source_location": f"L{_line_at(text, m.start())}", "kind": "class"})
        edges.append({"source": f_id, "target": cid, "relation": "contains",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})
        if parent and parent.split(".")[0] not in KEYWORDS:
            edges.append({"source": cid, "target": f"class::{parent}", "relation": "inherits",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})
        if impls:
            for iface in (t.strip() for t in impls.split(",")):
                if iface and iface.split(".")[0] not in KEYWORDS:
                    edges.append({"source": cid, "target": f"class::{iface}", "relation": "implements",
                                  "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---------------- functions & arrow consts -------------------------- #
    defined: set[str] = set(class_names)
    for regex in (RE_FUNCTION, RE_ARROW_FN):
        for m in regex.finditer(text):
            name = m.group(1)
            if name in defined or name in KEYWORDS:
                continue
            defined.add(name)
            fid = f"{rel}::{name}()"
            nodes.append({"id": fid, "label": f"{name}()", "file_type": "code", "source_file": rel,
                          "source_location": f"L{_line_at(text, m.start())}", "kind": "function"})
            edges.append({"source": f_id, "target": fid, "relation": "contains",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---------------- TS types ------------------------------------------ #
    for m in RE_TS_STRUCTS.finditer(text):
        name = m.group(1)
        if name in defined:
            continue
        defined.add(name)
        sid = f"{rel}::{name}"
        nodes.append({"id": sid, "label": name, "file_type": "code", "source_file": rel,
                      "source_location": f"L{_line_at(text, m.start())}", "kind": "type"})
        edges.append({"source": f_id, "target": sid, "relation": "contains",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---------------- calls --------------------------------------------- #
    seen_calls: set[tuple[str, str]] = set()
    for m in RE_CALL.finditer(text):
        receiver, callee = m.group(1), m.group(2)
        if callee in KEYWORDS:
            continue
        target = f"{receiver}.{callee}" if receiver and receiver not in KEYWORDS else callee
        if receiver and receiver in class_names:
            continue  # `new Foo(` handled by class nodes
        key = (f_id, target)
        if key in seen_calls:
            continue
        seen_calls.add(key)
        edges.append({"source": f_id, "target": f"symbol::{target}", "relation": "calls",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": rel, "symbol_hint": target})

    return {"nodes": nodes, "edges": _dedupe(edges)}
