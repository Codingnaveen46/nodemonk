"""nodemonk.extract - extraction facade.

Public surface:
    collect_files(root, categories) -> list[Path]
    extract(files, *, root, out_dir) -> {nodes, edges, ambiguities, cache_hits}
Extraction is deterministic, local, and LLM-free (semantic passes on docs run in
the assistant flow; the library itself is 100% offline).
"""

from __future__ import annotations

import json
import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from .python_ast import extract_python
from .javascript import extract_js
from .golang import extract_go
from .rust import extract_rust
from .jvm import extract_jvm
from .cfamily import extract_cfamily
from .markdown import extract_markdown
from .datafile import extract_datafile
from .binaryasset import extract_binary

# --------------------------------------------------------------------- #
# language dispatch

PY_EXTS = {".py", ".pyi"}
JS_EXTS = {".js", ".jsx", ".mjs", ".cjs", ".mts", ".vue", ".svelte", ".astro"}
TS_EXTS = {".ts", ".tsx", ".d.ts"}
GO_EXTS = {".go"}
RUST_EXTS = {".rs"}
JVM_EXTS = {".java", ".kt", ".kts", ".scala", ".groovy"}
C_EXTS = {".c", ".h", ".cpp", ".cc", ".cxx", ".c++", ".hpp", ".hh", ".hxx", ".cs", ".swift", ".m", ".mm"}
MD_EXTS = {".md", ".markdown", ".mdx", ".txt", ".rst", ".adoc"}
DATA_EXTS = {".json", ".geojson", ".jsonc", ".toml", ".yaml", ".yml", ".ini", ".cfg", ".csv", ".tsv", ".env"}
SQL_EXTS = {".sql"}
SH_EXTS = {".sh", ".bash", ".zsh", ".fish", ".ps1", ".bat", ".cmd", ".mk", ".make"}
OTHER_CODE = {".php", ".rb", ".pl", ".lua", ".ex", ".exs", ".erl", ".dart", ".zig",
              ".hs", ".jl", ".elm", ".sol", ".proto", ".graphql", ".vb", ".vfproj"}


def extractor_for(path: Path):  # -> Callable[[Path, str], dict] | None
    ext = path.suffix.lower()
    if ext in PY_EXTS:
        return extract_python
    if ext in TS_EXTS:
        return extract_js
    if ext in JS_EXTS:
        return extract_js
    if ext in GO_EXTS:
        return extract_go
    if ext in RUST_EXTS:
        return extract_rust
    if ext in JVM_EXTS:
        return extract_jvm
    if ext in C_EXTS:
        return extract_cfamily
    if ext in MD_EXTS:
        return extract_markdown
    if ext in DATA_EXTS:
        return extract_datafile_with(ext)
    if ext in SQL_EXTS or ext in SH_EXTS or ext in OTHER_CODE:
        return extract_markdown  # structural-free text: file node + references
    target = path.name.lower()
    if target.startswith(("dockerfile", "makefile", "gemfile", "justfile", "licen", "readme")):
        return extract_markdown
    cat = {
        ".png": "image", ".jpg": "image", ".jpeg": "image", ".gif": "image",
        ".webp": "image", ".mp4": "media", ".mov": "media", ".mp3": "media", ".wav": "media",
        ".pdf": "paper",
    }.get(ext)
    if cat:
        return lambda p, r: extract_binary(p, r, cat)
    return None


def extract_datafile_with(ext: str):
    """Close over the file's extension so the shared datafile extractor knows it."""
    def _inner(path: Path, rel: str) -> dict[str, Any]:
        return extract_datafile(path, rel, ext)
    return _inner


def collect_files(root: Path, categories: list[str] | None = None) -> list[Path]:
    """Expand a root into extractable file paths (categories filter optional)."""
    from ..detect import _classify, _walk

    wanted = set(categories or {"code", "document", "data", "paper", "image", "media"})
    out: list[Path] = []
    for f in _walk(root):
        if _classify(f) in wanted:
            out.append(f)
    return out


# --------------------------------------------------------------------- #
# cache

CACHE_NAME = ".extraction-cache.json"
CACHE_FORMAT = 3


def _cache_load(out_dir: Path | None) -> dict[str, Any]:
    if out_dir is None:
        return {"format": CACHE_FORMAT, "entries": {}}
    path = out_dir / CACHE_NAME
    if not path.exists():
        return {"format": CACHE_FORMAT, "entries": {}}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("format") == CACHE_FORMAT:
            return raw
    except (OSError, json.JSONDecodeError, ValueError):
        pass
    return {"format": CACHE_FORMAT, "entries": {}}


def _cache_save(out_dir: Path | None, cache: dict[str, Any]) -> None:
    if out_dir is None:
        return
    path = out_dir / CACHE_NAME
    try:
        path.write_text(json.dumps(cache), encoding="utf-8")
    except OSError:
        pass


def _process_one(args: tuple[str, str]) -> dict[str, Any]:
    path_str, rel = args
    from pathlib import Path as _P

    path = _P(path_str)
    fn = extractor_for(path)
    if fn is None:
        return {"nodes": [], "edges": []}
    try:
        return fn(path, rel)
    except Exception:  # noqa: BLE001 (extractors are best-effort; a bad file never kills a build)
        return {"nodes": [], "edges": []}


def extract(
    files: list[Path],
    *,
    root: Path,
    out_dir: Path | None = None,
    workers: int | None = None,
) -> dict[str, Any]:
    """Extract all files under root -> merged {nodes, edges, resolved}.

    Uses cache keyed by (relpath, sha); parallel workers above 800 files.
    """
    from ..detect import _hash_and_count

    cache = _cache_load(out_dir)
    pending: list[tuple[Path, str]] = []
    cached_fragments: dict[str, dict[str, Any]] = {}
    cache_hits = 0

    rels: dict[Path, str] = {}
    for f in files:
        try:
            rels[f] = str(f.relative_to(root))
        except ValueError:
            rels[f] = f.name

    for f in files:
        rel = rels[f]
        sha, _mtime, _size, _w = _hash_and_count(f)  # already computed in detect; recompute cheap
        if out_dir is not None:
            entry = cache["entries"].get(rel)
            if entry and entry.get("sha") == sha:
                cached_fragments[rel] = entry["payload"]
                cache_hits += 1
                continue
        pending.append((f, sha))

    new_results: dict[str, dict[str, Any]] = {}
    payloads: dict[str, dict[str, Any]] = {}

    if pending:
        if len(pending) >= 800:
            n_workers = max(2, (os.cpu_count() or 4) - 1) if workers is None else max(1, workers)
            with ProcessPoolExecutor(max_workers=n_workers) as pool:
                args = [(str(f), rels[f]) for f, _sha in pending]
                outs = list(pool.map(_process_one, args, chunksize=32))
            for (f, sha), payload in zip(pending, outs):
                rel = rels[f]
                payloads[rel] = payload
                cache["entries"][rel] = {"sha": sha, "payload": payload}
        else:
            for f, sha in pending:
                rel = rels[f]
                payload = _process_one((str(f), rel))
                payloads[rel] = payload
                cache["entries"][rel] = {"sha": sha, "payload": payload}

    _cache_save(out_dir, cache)

    # -------- merge named fragments -------- #
    all_nodes: list[dict[str, Any]] = []
    all_edges: list[dict[str, Any]] = []
    seen_nodes: set[str] = set()
    node_index: dict[str, dict[str, Any]] = {}
    for rel in sorted(cached_fragments):
        for nd in cached_fragments[rel].get("nodes", []):
            if nd["id"] not in seen_nodes:
                seen_nodes.add(nd["id"])
                node_index[nd["id"]] = nd
                all_nodes.append(nd)
        all_edges.extend(cached_fragments[rel].get("edges", []))
    for rel in sorted(payloads):
        for nd in payloads[rel].get("nodes", []):
            if nd["id"] not in seen_nodes:
                seen_nodes.add(nd["id"])
                node_index[nd["id"]] = nd
                all_nodes.append(nd)
        all_edges.extend(payloads[rel].get("edges", []))

    # -------- cross-file resolution -------- #
    resolved_nodes, resolved_edges, resolutions = resolve(all_nodes, all_edges, root)

    resolved_nodes.sort(key=lambda nd: (nd.get("source_file", ""), nd.get("kind", ""), nd["id"]))
    return {
        "nodes": resolved_nodes,
        "edges": resolved_edges,
        "resolutions": resolutions,
        "cache_hits": cache_hits,
        "input_tokens": 0,
        "output_tokens": 0,
    }


# --------------------------------------------------------------------- #
# cross-file resolution
# imported lazily to avoid a circular import

def resolve(nodes, edges, root: Path):  # type: ignore[no-untyped-def]
    from .resolution import resolve_graph

    return resolve_graph(nodes, edges, root)
