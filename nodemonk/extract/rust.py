"""Rust extractor (structural regex, stdlib-only)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

RE_IMPORT = re.compile(r"^[\t ]*use\s+([\w:*\-{}, ]+);", re.M)
RE_MOD = re.compile(r"^[\t ]*(?:pub(?:\([\w]+\))?\s+)?mod\s+(\w+)\s*[{;]", re.M)
RE_FN = re.compile(r"^[\t ]*(?:pub(?:\([\w]+\))?\s+)?(?:const\s+)?(?:unsafe\s+)?(?:extern\s+\"?\w+\"?\s+)?(?:async\s+)?fn\s+(\w+)", re.M)
RE_STRUCT = re.compile(r"^[\t ]*(?:pub(?:\([\w]+\))?\s+)?(?:struct|enum|union)\s+(\w+)", re.M)
RE_TRAIT = re.compile(r"^[\t ]*(?:pub(?:\([\w]+\))?\s+)?trait\s+(\w+)", re.M)
RE_IMPL = re.compile(r"^[\t ]*impl(?:<[^>]*>)?\s+(?:[\w:]+\s+for\s+)?([\w:]+)", re.M)
RE_CALLS = re.compile(r"(?:([\w:]+)\.)?([A-Za-z_][\w]*)\s*(?:::<[^>]*>)?\(", re.S)

BUILTINS = {
    "if", "else", "while", "loop", "for", "match", "return", "if_let",
    "println", "print", "eprintln", "eprint", "vec", "format", "todo",
    "unimplemented", "panic", "assert", "assert_eq", "assert_ne", "debug_assert",
    "write", "writeln", "drop", "matches", "max", "min", "iter", "clone",
    "new", "default", "from", "into", "to_string", "as_str", "as_bytes",
    "len", "push", "pop", "is_empty", "map", "filter", "collect", "unwrap",
}


def file_id(rel: str) -> str:
    return f"file::{rel}"


def extract_rust(path: Path, rel: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4_000_000]
    except OSError:
        return {"nodes": [], "edges": []}

    f_id = file_id(rel)
    nodes: list[dict[str, Any]] = [
        {"id": f_id, "label": Path(path).name, "file_type": "code", "source_file": rel}
    ]
    edges: list[dict[str, Any]] = []

    # ---- uses ---------------------------------------------------------- #
    uses: set[str] = set()
    for m in RE_IMPORT.finditer(text):
        path_part = m.group(1).split(";")[0]
        # keep the top crate / module segment e.g. `std::collections::HashMap`
        segments = [s.strip() for s in path_part.split("::") if s.strip() and s.strip() != "*"]
        if segments:
            uses.add("::".join(segments[: max(1, len(segments) - 1)] or segments))
    for u in sorted(uses):
        edges.append({"source": f_id, "target": f"module::{u}", "relation": "imports",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---- mods ---------------------------------------------------------- #
    for m in RE_MOD.finditer(text):
        name = m.group(1)
        mid = f"{rel}::mod::{name}"
        nodes.append({"id": mid, "label": f"mod {name}", "file_type": "code", "source_file": rel,
                      "kind": "module"})
        edges.append({"source": f_id, "target": mid, "relation": "contains",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---- structs / enums / traits -------------------------------------- #
    defined: set[str] = set()
    for regex, kind, rel_kind in (
        (RE_STRUCT, "struct", "struct"),
        (RE_TRAIT, "trait", "trait"),
    ):
        for m in regex.finditer(text):
            name = m.group(1)
            if name in defined:
                continue
            defined.add(name)
            sid = f"{rel}::{name}"
            nodes.append({"id": sid, "label": name, "file_type": "code", "source_file": rel,
                          "source_location": f"L{text.count(chr(10), 0, m.start()) + 1}", "kind": rel_kind})
            edges.append({"source": f_id, "target": sid, "relation": "contains",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---- impls -> tie them to the type they implement -------------------- #
    for m in RE_IMPL.finditer(text):
        type_name = m.group(1).split("::")[-1]
        tid = f"{rel}::{type_name}"
        if type_name in defined:
            edges.append({"source": f_id, "target": tid, "relation": "implements",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---- functions ------------------------------------------------------- #
    fns: set[str] = set()
    for m in RE_FN.finditer(text):
        name = m.group(1)
        if name in fns or name in BUILTINS:
            continue
        fns.add(name)
        fid = f"{rel}::{name}()"
        nodes.append({"id": fid, "label": f"{name}()", "file_type": "code", "source_file": rel,
                      "source_location": f"L{text.count(chr(10), 0, m.start()) + 1}", "kind": "function"})
        edges.append({"source": f_id, "target": fid, "relation": "contains",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---- calls ------------------------------------------------------------ #
    seen: set[tuple[str, str]] = set()
    for m in RE_CALLS.finditer(text):
        recv, callee = m.group(1), m.group(2)
        if callee in BUILTINS:
            continue
        target = f"{recv}::{callee}" if recv and "::" not in recv else (f"{recv}.{callee}" if recv else callee)
        key = (f_id, target)
        if key in seen:
            continue
        seen.add(key)
        edges.append({"source": f_id, "target": f"symbol::{target}", "relation": "calls",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel,
                      "symbol_hint": target})

    seen3: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for e in edges:
        k = (e["source"], e["target"], e["relation"])
        if k in seen3:
            continue
        seen3.add(k)
        out.append(e)
    return {"nodes": nodes, "edges": out}
