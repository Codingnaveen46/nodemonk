"""Python AST extractor - deterministic, stdlib-only, free.

Nodes: file, class, function.  Edges: contains, inherits, imports, calls.
Calls discovered here point at `symbol::name` stubs; the resolution pass in
nodemonk/extract/resolution.py swaps those stubs for real node ids (same-file
matches stay EXTRACTED, cross-file matches become INFERRED).
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


def file_node_id(rel: str) -> str:
    return f"file::{rel}"


def node_id(rel: str, qualname: str) -> str:
    return f"{rel}::{qualname}"


def extract_python(path: Path, rel: str) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    file_id = file_node_id(rel)

    try:
        source = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(source)
    except (SyntaxError, ValueError, OSError):
        nodes.append({"id": file_id, "label": Path(path).name, "file_type": "code", "source_file": rel})
        return {"nodes": nodes, "edges": edges}

    nodes.append({"id": file_id, "label": Path(path).name, "file_type": "code", "source_file": rel})
    file_docstring = ast.get_docstring(tree)
    if file_docstring:
        nodes[-1]["docstring"] = file_docstring[:500]

    parents: list[tuple[str, str]] = []  # dotted names + node ids

    # ---------------- pass 1: definitions ------------------------------ #
    class DefVisitor(ast.NodeVisitor):
        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            qualname = ".".join([p[0] for p in parents] + [node.name])
            nid = node_id(rel, qualname)
            entry: dict[str, Any] = {
                "id": nid,
                "label": qualname,
                "file_type": "code",
                "source_file": rel,
                "source_location": f"L{node.lineno}",
                "kind": "class",
            }
            doc = ast.get_docstring(node)
            if doc:
                entry["docstring"] = doc[:500]
            nodes.append(entry)
            container = parents[-1][1] if parents else file_id
            edges.append({"source": container, "target": nid, "relation": "contains",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})
            for base in node.bases:
                try:
                    base_name = ast.unparse(base)
                except Exception:  # noqa: BLE001 (exotic base expressions)
                    base_name = ""
                if base_name:
                    edges.append({"source": nid, "target": f"class::{base_name}",
                                  "relation": "inherits", "confidence": "EXTRACTED",
                                  "confidence_score": 1.0, "source_file": rel})
            parents.append((node.name, nid))
            self.generic_visit(node)
            parents.pop()

        def _visit_func(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            qualname = ".".join([p[0] for p in parents] + [node.name])
            nid = node_id(rel, qualname)
            entry = {
                "id": nid,
                "label": qualname + "()",
                "file_type": "code",
                "source_file": rel,
                "source_location": f"L{node.lineno}",
                "kind": "function",
                "async": isinstance(node, ast.AsyncFunctionDef),
            }
            doc = ast.get_docstring(node)
            if doc:
                entry["docstring"] = doc[:500]
            nodes.append(entry)
            container = parents[-1][1] if parents else file_id
            edges.append({"source": container, "target": nid, "relation": "contains",
                          "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})
            parents.append((node.name, nid))
            self.generic_visit(node)
            parents.pop()

        visit_FunctionDef = _visit_func
        visit_AsyncFunctionDef = _visit_func

    DefVisitor().visit(tree)

    # ---------------- pass 2: imports ---------------------------------- #
    modules: set[str] = set()
    for blk in ast.walk(tree):
        if isinstance(blk, ast.Import):
            modules.update(alias.name for alias in blk.names)
        elif isinstance(blk, ast.ImportFrom) and blk.module:
            modules.add("." * blk.level + blk.module)
    for mod in sorted(modules):
        edges.append({"source": file_id, "target": f"module::{mod}", "relation": "imports",
                      "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": rel})

    # ---------------- pass 3: calls per owning scope -------------------- #
    scopes: list[tuple[str, ast.AST]] = [(file_id, tree)]

    class ScopeVisitor(ast.NodeVisitor):
        prefix: list[str] = []

        def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
            self._enter(node)

        def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
            self._enter(node)

        def _enter(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
            qual = ".".join(self.prefix + [node.name])
            self.prefix.append(node.name)
            scopes.append((node_id(rel, qual), node))
            self.generic_visit(node)
            self.prefix.pop()

        def visit_ClassDef(self, node: ast.ClassDef) -> None:
            self.prefix.append(node.name)
            self.generic_visit(node)
            self.prefix.pop()

    ScopeVisitor().visit(tree)

    seen_calls: set[tuple[str, str]] = set()
    for owner_id, scope in scopes:
        for sub in ast.walk(scope):
            if not isinstance(sub, ast.Call):
                continue
            fn = sub.func
            if isinstance(fn, ast.Name):
                target = fn.id
            elif isinstance(fn, ast.Attribute):
                try:
                    target = ast.unparse(fn)
                except Exception:  # noqa: BLE001
                    target = fn.attr
            else:
                continue
            key = (owner_id, target)
            if key in seen_calls:
                continue
            seen_calls.add(key)
            edges.append({"source": owner_id, "target": f"symbol::{target}",
                          "relation": "calls", "confidence": "EXTRACTED",
                          "confidence_score": 1.0, "source_file": rel, "symbol_hint": target})

    seen: set[tuple[str, str, str]] = set()
    final: list[dict[str, Any]] = []
    for e in edges:
        key = (e["source"], e["target"], e["relation"])
        if key in seen:
            continue
        seen.add(key)
        final.append(e)
    return {"nodes": nodes, "edges": final}
