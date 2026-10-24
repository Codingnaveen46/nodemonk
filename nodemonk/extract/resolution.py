"""Cross-file resolution - where extraction stubs become real graph edges.

Extraction produces intentional stub targets:
    symbol::<name>            (calls/mentions)   -> resolve against a symbol index
    class::<Name>             (inherits)         -> resolve against a class index
    module::<dotted/relative> (imports/includes) -> resolve to `file::rel` nodes
    file::<rel>               (doc references)   -> keep only if the file exists in corpus
Unresolvable `symbol::`/`class::` stubs are dropped (they carry no information);
unresolvable `module::` targets become visible "external dependency" nodes.
Direction stays EXTRACTED for same-file matches and INFERRED (0.85) when the
match crosses files - never silently upgraded.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

CONF_RANK = {"EXTRACTED": 0, "INFERRED": 1, "AMBIGUOUS": 2}


def resolve_graph(nodes, edges, root: Path):  # type: ignore[no-untyped-def]
    """Returns (resolved_nodes, resolved_edges, stats)."""
    node_index: dict[str, dict[str, Any]] = {}
    for nd in nodes:
        node_index[nd["id"]] = nd
        node_index.setdefault(nd["id"], {}).setdefault("file_type", "code")

    corpus_files: set[str] = {
        nd["id"] for nd in nodes if nd["id"].startswith("file::")
    }
    # NOTE: `rel` inside file ids is the corpus-relative posix path
    file_rel = {nd["id"][6:]: nd for nd in nodes if nd["id"].startswith("file::")}

    # ---------------- module resolution indexes ------------------------- #
    module_map: dict[str, set[str]] = {}

    def index_modules(target: str, fid: str) -> None:
        stem = target[:-1 * len(Path(target).suffix)] if Path(target).suffix else target
        parts = stem.split("/")
        for k in (1, 2, 3):
            if len(parts) >= k:
                module_map.setdefault(".".join(parts[-k:]), set()).add(fid)
        module_map.setdefault(stem, set()).add(fid)
        module_map.setdefault(parts[-1], set()).add(fid)

    for rel in file_rel:
        index_modules(rel, f"file::{rel}")

    # ------------------------------------------------------------------ #
    # symbol indexes: bare name and dotted qualname

    sym_by_qualname: dict[str, set[str]] = {}
    sym_by_bare: dict[str, set[str]] = {}
    class_by_bare: dict[str, set[str]] = {}

    for nd in nodes:
        nid = nd["id"]
        if nid.startswith(("file::", "module::", "symbol::", "class::", "url::", "cite::", "asset::")):
            continue
        label = nd.get("label", "")
        bare = label[:-2] if label.endswith("()") else label
        sym_by_bare.setdefault(bare, set()).add(nid)
        if nd.get("kind") == "class" or nd.get("kind") == "type" or nd.get("kind") in (
            "struct", "interface", "trait", "enum", "record", "object", "recv",
        ):
            class_by_bare.setdefault(bare, set()).add(nid)

    # python specific: dotted qualname -> id list (rel::qual style)
    for nid in node_index:
        base, sep, qual = nid.partition("::")
        if sep and not base.startswith(("file", "module", "symbol", "class", "url", "cite", "asset", "package")):
            last_dotted = qual.split(".")[-2:]
            for k in (1, 2):
                if len(qual.split(".")) >= k:
                    dotted = ".".join(qual.split(".")[-k:])
                    sym_by_qualname.setdefault(dotted, set()).add(nid)
        for sub in nid.split("::")[-1].split("."):
            if sub:
                sym_by_qualname.setdefault(sub, set()).add(nid)

    # ---------------- edge repair -------------------------------------- #
    stats = {"symbol_edges": 0, "class_edges": 0, "module_edges": 0,
             "dropped_stub": 0, "external_module_edges": 0, "deduped": 0}

    out_edges: list[dict[str, Any]] = []
    dropped_ids: set[str] = set()

    def resolve_symbol(hint: str) -> tuple[str | None, str]:
        """Best-effort symbol target. Returns (node_id_or_None, confidence)."""
        cands: set[str] = set()
        # 1. exact dotted hint (Class.method / fn)
        cands |= sym_by_qualname.get(hint, set()) | sym_by_qualname.get(hint + "()", set())
        # 2. receivers: Type Receiver.method  -> Type.method / method
        selectors = [hint]
        if "." in hint:
            pieces = hint.split(".")
            selectors.append(pieces[-1])
            type_name = pieces[0]
            if "." in type_name:
                type_name = type_name.split(".")[-1]
            cands |= sym_by_qualname.get(f"{type_name}.{pieces[-1]}", set())
            selectors.append(f"{type_name}.{pieces[-1]}")
        if "::" in hint:
            last = hint.split("::")[-1]
            selectors.append(last)
        for sel in selectors:
            cands |= sym_by_bare.get(sel, set())
        if not cands:
            return None, "EXTRACTED"
        if len(cands) <= 4:
            ranker = []
            for cid in cands:
                rank = (len(cid.split(".")) < 3, cid.count("/"), len(cid))
                ranker.append((rank, cid))
            ranker.sort(key=lambda t: t[0])
            return ranker[0][1], ("EXTRACTED" if ranker[0][0][0] == 0 else "INFERRED")
        return None, "AMBIGUOUS"

    for e in edges:
        src, tgt, relation = e.get("source"), e.get("target"), e.get("relation")
        if not tgt:
            dropped_ids.add(tgt or "")
            stats["dropped_stub"] += 1
            continue
        if src not in node_index and relation in ("references", "imports", "includes", "section", "contains", "links_to"):
            # source is a markdown-created stub file that did not survive dedupe: skip
            stats["dropped_stub"] += 1
            continue
        if src not in node_index:
            # caller node never materialised (extraction drift); skip the edge
            stats["dropped_stub"] += 1
            continue
        if tgt.startswith("symbol::"):
            hint = tgt[len("symbol::"):]
            if e.get("symbol_hint"):
                hint = e["symbol_hint"]
            nid, conf = resolve_symbol(hint)
            if nid is None:
                stats["dropped_stub"] += 1
                continue
            e2 = dict(e)
            e2["target"] = nid
            e2.pop("symbol_hint", None)
            src_domain = src.split("::")[0].split("/")[0]
            tgt_domain = nid.split("::")[0].split("/")[0]
            if conf == "EXTRACTED" and src_domain != tgt_domain:
                conf = "INFERRED"
                e2["confidence"] = "INFERRED"
                e2["confidence_score"] = 0.85
            out_edges.append(e2)
            stats["symbol_edges"] += 1
        elif tgt.startswith("class::"):
            hint = tgt[len("class::"):]
            cands = class_by_bare.get(hint, set())
            if len(cands) == 1:
                e2 = dict(e)
                e2["target"] = next(iter(cands))
                out_edges.append(e2)
                stats["class_edges"] += 1
            elif len(cands) > 1:
                same = [c for c in cands if c.split("::")[0] == e.get("source", "::").split("::")[0]]
                if same:
                    e2 = dict(e)
                    e2["target"] = sorted(same)[0]
                    out_edges.append(e2)
                    stats["class_edges"] += 1
                else:
                    for cid in sorted(cands)[:2]:
                        e2 = dict(e)
                        e2["target"] = cid
                        e2["confidence_score"] = 0.4
                        e2["confidence"] = "AMBIGUOUS"
                        out_edges.append(e2)
                    stats["class_edges"] += 1
            else:
                stats["dropped_stub"] += 1
        elif tgt.startswith("module::"):
            spec = tgt[len("module::"):]
            match = match_module(spec, e.get("source", ""), corpus_files, module_map, file_rel)
            if match:
                e2 = dict(e)
                e2["target"] = match
                out_edges.append(e2)
                stats["module_edges"] += 1
            else:
                keep = dict(e)
                get_node(node_index, nodes, tgt, "external dependency")
                out_edges.append(keep)
                stats["external_module_edges"] += 1
        elif tgt.startswith("file::"):
            rel_target = tgt[len("file::"):]
            if tgt in corpus_files or f"file::{Path(rel_target).as_posix()}" in corpus_files:
                e2 = dict(e)
                if tgt not in corpus_files:
                    e2["target"] = f"file::{Path(rel_target).as_posix()}"
                out_edges.append(e2)
            else:
                stats["dropped_stub"] += 1
        else:
            out_edges.append(e)

    # ---- dedupe: same (u,v,relation) keep the most confident version ------ #
    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for e in out_edges:
        key = (e.get("source", ""), e.get("target", ""), e.get("relation", ""))
        existing = best.get(key)
        if existing is None or CONF_RANK.get(e.get("confidence", ""), 2) < CONF_RANK.get(existing.get("confidence", ""), 2):
            best[key] = e
    final_edges = list(best.values())
    stats["deduped"] = len(out_edges) - len(final_edges)

    return nodes, final_edges, stats


def get_node(node_index: dict[str, dict[str, Any]], nodes: list, nid: str, label: str) -> dict[str, Any]:
    if nid not in node_index:
        nd = {"id": nid, "label": label, "file_type": "code", "external": True}
        node_index[nid] = nd
        nodes.append(nd)
    return node_index[nid]


def match_module(spec: str, source: str, rels: set[str], module_map: dict[str, set[str]], file_rel: dict[str, Any]) -> str | None:  # type: ignore[name-defined]
    # python-style dotted from source's own directory
    src_dir = source.split("::")[-1]
    candidates: set[str] = set()
    if spec.startswith("."):
        depth = len(spec) - len(spec.lstrip("."))
        rest = spec[depth:]
        base = src_dir.split("/")
        base = base[: len(base) - depth] if depth <= len(base) else []
        rel_path = "/".join([*base, rest.replace(".", "/")])
        for cand in (rel_path, os.path.join(rel_path, "__init__"), f"{rel_path}.pyi", f"{rel_path}.py"):
            if f"file::{cand}" in rels:
                return f"file::{cand}"
        candidates = module_map.get(rest.replace("/", "."), set())
        if candidates:
            return sorted(candidates)[0]
        return None
    # absolute dotted or path-style
    spec_norm = spec.replace("/", ".")
    if f"file::{spec}" in rels:
        return f"file::{spec}"
    for k in (3, 2, 1):
        parts = spec_norm.split(".")
        if len(parts) >= k:
            matches = module_map.get(".".join(parts[-k:]))
            if matches:
                return sorted(matches)[0]
    return None
