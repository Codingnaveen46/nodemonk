"""Go extractor (structural regex, stdlib-only)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

RE_PACKAGE = re.compile(r"^[\t ]*package\s+([\w/.]+)", re.M)
RE_IMPORTS = re.compile(r"^(?:\t|    )?(?:import\s+(?:\(?\s*)?)?[\t ]*(?:_|\w+)?\s*\"([\w/.\-]+)\"", re.M)
RE_IMPORT_BLOCK = re.compile(r"^[\t ]*import\s*\(([^)]*)\)", re.M | re.S)
RE_FUNC = re.compile(r"^[\t ]*func\s+(?:\(\s*\w+\s+\*?([\w./]+)\s*\)\s*)?([A-Za-z_][\w]*)\s*(?:\[?[^{]*\])?\(", re.M)
RE_TYPE = re.compile(r"^[\t ]*type\s+([A-Za-z_][\w]*)\s+(struct|interface)\b", re.M)
RE_CALLS = re.compile(r"(?:([\w.]+)\.)?([A-Za-z_][\w]*)\s*\(", re.S)


def file_id(rel: str) -> str:
    return f"file::{rel}"


def extract_go(path: Path, rel: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4_000_000]
    except OSError:
        return {"nodes": [], "edges": []}

    f_id = file_id(rel)
    nodes: list[dict[str, Any]] = [{"id": f_id, "label": Path(path).name, "file_type": "code", "source_file": rel}]
    edges: list[dict[str, Any]] = []

    packages = RE_PACKAGE.findall(text)
    pkg = packages[0] if packages else Path(path).stem

    # ---- imports (single statements + parenthesized blocks) ------------ #
    import_targets: set[str] = set()
    for m in RE_IMPORT_BLOCK.finditer(text):
        import_targets.update(
            t.strip().split()[-1].strip('"') for t in m.group(1).splitlines() if t.strip()
        )
    import_targets.update(RE_IMPORTS.findall(text))
    import_targets = {t for t in import_targets if "/" in t or "." in t}
    for target in sorted(import_targets):
        edges.append({"source": f_id, "target": f"module::{target}", "relation": "imports",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---- types ---------------------------------------------------------- #
    for m in RE_TYPE.finditer(text):
        name, kind = m.group(1), m.group(2)
        tid = f"{rel}::{name}"
        nodes.append({"id": tid, "label": name, "file_type": "code", "source_file": rel,
                      "source_location": f"L{text.count(chr(10), 0, m.start()) + 1}", "kind": kind})
        edges.append({"source": f_id, "target": tid, "relation": "contains",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---- functions (methods attach to their receiver type if known) ----- #
    defined: set[str] = set()
    method_ids: list[tuple[str, str]] = []  # (callee_letter_id, receiver_type)
    for m in RE_FUNC.finditer(text):
        recv, name = m.group(1), m.group(2)
        if name in defined:
            continue
        defined.add(name)
        fid = f"{rel}::{name}"
        label = f"{name}()"
        if recv:
            label = f"{recv}.{name}()"
        nodes.append({"id": fid, "label": label, "file_type": "code", "source_file": rel,
                      "source_location": f"L{text.count(chr(10), 0, m.start()) + 1}", "kind": "function"})
        if recv:
            # method: node for the *receivable type* via class:: stub
            method_ids.append((fid, recv))
            edges.append({"source": f_id, "target": fid, "relation": "contains",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})
        else:
            edges.append({"source": f_id, "target": fid, "relation": "contains",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # method containment: function tidied under its type IF the type is local
    # (resolution.py later can promote to Type -> contains Method where known)
    for fid, recv in method_ids:
        local_type = f"{rel}::{recv}"
        nodes.append({"id": local_type, "label": recv, "file_type": "code", "source_file": rel, "kind": "recv"})
        edges.append({"source": local_type, "target": fid, "relation": "contains",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---- calls ----------------------------------------------------------- #
    seen: set[tuple[str, str]] = set()
    receiver_vars = {"t", "s", "b", "r", "w", "c"}  # single-letter receiver noise
    for m in RE_CALLS.finditer(text):
        recv, callee = m.group(1), m.group(2)
        if callee in {"if", "for", "switch", "len", "cap", "make", "new", "append",
                      "delete", "copy", "panic", "recover", "go", "defer", "print",
                      "println", "close", "complex", "real", "imag", "min", "max"}:
            continue
        if recv in receiver_vars:
            target = callee
        else:
            target = f"{recv}.{callee}" if recv else callee
        key = (f_id, target)
        if key in seen:
            continue
        seen.add(key)
        edges.append({"source": f_id, "target": f"symbol::{target}", "relation": "calls",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel,
                      "symbol_hint": target})

    # dedupe
    seen3: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for e in edges:
        k = (e["source"], e["target"], e["relation"])
        if k in seen3:
            continue
        seen3.add(k)
        out.append(e)
    return {"nodes": nodes, "edges": out}
