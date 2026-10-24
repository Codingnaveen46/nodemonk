"""C / C++ / C# extractor (structural regex, stdlib-only) - pragmatic breadth."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

RE_INCLUDE = re.compile(r"^[ \t]*#\s*include\s+[<\"]([^<\">]+)[>\"]", re.M)
RE_HEADER_GUARDFUNC = re.compile(r"^[ \t]*(?:__\w+[ \t]+)?(?:[A-Za-z_][\w]*)?[ \t]+\**([A-Za-z_][\w]*)\s*\(([^;]*)\)\s*(?:const)?\s*;?", re.M)
RE_FN_DEF = re.compile(
    r"^[ \t]*(?:__\w+[ \t]+)?(?:static\s+|inline\s+|virtual\s+|const\b\s*|constexpr\s+|extern\s+|override\s+|public\s+|private\s+|protected\s+)*"
    r"[\w:<>\*&]+[ \t\*&]+(?:[\w:<>&\*]+::)*([A-Za-z_][\w]*)\s*(?:<[^>;]*>)?\s*\(([^;{}]*?)\)\s*(?:const|override|noexcept|[\w\s,&]*)?[ \t]*\{",
    re.M,
)
RE_CLASSLIKE = re.compile(
    r"^[ \t]*(?:export\s+)?(?:@[\w]+(?:\s*\([^)]*\))?\s+)*"
    r"(?:[\w]+\s+)*"
    r"(?:class|struct|interface|enum|namespace|record)\s+([A-Za-z_][\w]*)"
    r"([^\n;{]*)",
    re.M | re.U,
)
RE_USING = re.compile(r"^[ \t]*using\s+(?:namespace\s+)?([\w.:]+)\s*;", re.M)


def file_id(rel: str) -> str:
    return f"file::{rel}"


def extract_cfamily(path: Path, rel: str) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")[:4_000_000]
    except OSError:
        return {"nodes": [], "edges": []}

    f_id = file_id(rel)
    nodes: list[dict[str, Any]] = [
        {"id": f_id, "label": Path(path).name, "file_type": "code", "source_file": rel}
    ]
    edges: list[dict[str, Any]] = []

    for m in RE_INCLUDE.finditer(text):
        edges.append({"source": f_id, "target": f"module::{m.group(1)}", "relation": "includes",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})
    for m in RE_USING.finditer(text):
        edges.append({"source": f_id, "target": f"module::{m.group(1)}", "relation": "imports",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---- definitional regex used to avoid matching declarations in headers -- #
    fn_names: set[str] = set()
    for m in RE_FN_DEF.finditer(text):
        name = m.group(1)
        signature = m.group(2) or ""
        if name in {"if", "for", "while", "switch", "sizeof", "return", "catch"}:
            continue
        if name in fn_names:
            continue
        fn_names.add(name)
        fid = f"{rel}::{name}()"
        nodes.append({"id": fid, "label": f"{name}()", "file_type": "code", "source_file": rel,
                      "source_location": f"L{text.count(chr(10), 0, m.start()) + 1}", "kind": "function",
                      "args": signature[:120]})
        edges.append({"source": f_id, "target": fid, "relation": "contains",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---- class-like declarations ------------------------------------------ #
    type_names: set[str] = set()
    for m in RE_CLASSLIKE.finditer(text):
        name, tail = m.group(1), (m.group(2) or "").strip()
        if name in type_names or name in fn_names:
            continue
        type_names.add(name)
        tid = f"{rel}::{name}"
        nodes.append({"id": tid, "label": name, "file_type": "code", "source_file": rel,
                      "source_location": f"L{text.count(chr(10), 0, m.start()) + 1}", "kind": "type"})
        edges.append({"source": f_id, "target": tid, "relation": "contains",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})
        for sep in (": public", ": private", ": protected", " extends ", " : ", " implements "):
            if sep in tail:
                after = tail.split(sep, 1)[1]
                for base in (b.strip().split("<")[0].split(".")[0] for b in after.split(",")):
                    if base and re.fullmatch(r"[A-Za-z_][\w]*", base):
                        edges.append({"source": tid, "target": f"class::{base}", "relation": "inherits",
                                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})
                break

    # ---- calls: cited through callee name resolution later ------------------ #
    seen: set[tuple[str, str, str]] = set()
    out: list[dict[str, Any]] = []
    for e in edges:
        k = (e["source"], e["target"], e["relation"])
        if k in seen:
            continue
        seen.add(k)
        out.append(e)
    return {"nodes": nodes, "edges": out}