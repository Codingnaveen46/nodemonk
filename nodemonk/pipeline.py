"""nodemonk.pipeline - detect -> extract -> build -> cluster -> analyze -> report -> export."""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from . import OUT_DIR_NAME, __version__
from .analyze import (bridges_and_articulation, confidence_profile,
                      find_cycles, god_nodes, locate_isolated,
                      suggest_questions, surprising_connections)
from .cluster import (cluster, label_communities_by_hub, modularity,
                      score_all, cohesion_score)
from .build import build_from_extraction
from .detect import detect, top_subdirs
from .extract import extract as extract_files
from .fsutil import atomic_write
from .graph import Graph
from .manifest import detect_incremental, load_manifest, save_manifest
from .query import global_stats
from .report import generate as generate_report
from .export import to_cypher, to_dot, to_graphml, to_json, to_obsidian, to_svg, load_graph_file
from .viz import write_viz_html
from .wiki import to_wiki
from .callflow import to_callflow_html

COST_FILE = "cost-history.json"


def run_pipeline(
    root: Path,
    out_dir: Path | None = None,
    *,
    update: bool = False,
    code_only_update: bool = False,
    resolution: float = 1.0,
    ambiguous_scale: float = 0.5,
    workers: int | None = None,
    max_files: int = 0,
    quiet: bool = False,
    html: bool = True,
    svg: bool = False,
    graphml: bool = False,
    cypher: bool = False,
    dot: bool = False,
    obsidian: bool = False,
    wiki: bool = False,
    callflow: bool = False,
    exclude_hubs: int = 0,
) -> dict[str, Any]:
    root = Path(root).resolve()
    if not root.exists():
        raise FileNotFoundError(f"scan root does not exist: {root}")
    out_dir = Path(out_dir) if out_dir is not None else root / OUT_DIR_NAME
    out_dir.mkdir(parents=True, exist_ok=True)

    def say(msg: str) -> None:
        if not quiet:
            print(msg, flush=True)

    # -------------------------------------------------- detection
    if update and load_manifest(out_dir) is not None:
        incr = detect_incremental(root, out_dir)
        detection = {
            "scan_root": str(root),
            "category_counts": {c: len(v) for c, v in incr["all_files"].items()},
            "categories": incr["all_files"],
            "total_files": incr["total_files"],
            "total_words": incr["total_words"],
            "warning": None,
        }
        say(
            f"corpus: {incr['total_files']:,} files ~{incr['total_words']:,} words"
            f"; --update sees {incr['new_total']:,} new/changed"
        )
    else:
        detection = detect(root, max_files=max_files, workers=workers)
        incr = {
            "all_files": detection["categories"],
            "new_files": detection["categories"],
            "new_total": detection["total_files"],
            "unchanged": 0,
            "extraction": "mixed",
        }
        cats = detection["category_counts"]
        cat_line = " · ".join(f"{c}: {n}" for c, n in sorted(cats.items(), key=lambda kv: -kv[1]))
        say(f"corpus: {detection['total_files']:,} files ~{detection['total_words']:,} words ({cat_line})")

    if detection["total_files"] == 0:
        return {"error": f"no supported files found in {root}", "out_dir": str(out_dir)}
    if detection["total_words"] > 2_000_000:
        say(f"corpus is large (~{detection['total_words']:,} words) - nodemonk has no cap, proceeding in full")

    # -------------------------------------------------- extract
    targets: list[Path] = []
    wanted_cats = {"code"} if code_only_update else {"code", "document", "data", "paper", "image", "media"}
    for cat, rels in incr["all_files"].items():
        if update:
            changed = set(incr["new_files"].get(cat, []))
            if cat in ("code",) or not (set(rels) - changed):
                # code files are cached by hash anyway - everything lands here
                targets.extend((root / r1) for r1 in rels)
            else:
                codes = set(incr["new_files"].get("code", []))
                targets.extend((root / r1) for r1 in (changed | codes) if (root / r1).exists())
        else:
            if cat in wanted_cats:
                targets.extend((root / r1) for r1 in rels)
    targets = [t for t in targets if t.exists()]

    say(f"extracting {len(targets):,} files (deterministic, zero tokens)...")
    extraction = extract_files(targets, root=root, out_dir=out_dir, workers=workers)
    nodes = extraction["nodes"]
    edges = extraction["edges"]
    say(
        f"extraction: {len(nodes):,} nodes · {len(edges):,} raw edges "
        f"(symbol-edged: {extraction['resolutions'].get('symbol_edges', 0):,}, "
        f"module-edged: {extraction['resolutions'].get('module_edges', 0):,}, "
        f"module nodes: {extraction['resolutions'].get('external_module_edges', 0):,}, "
        f"cache hits: {extraction['cache_hits']:,})"
    )

    # -------------------------------------------------- build (+ merge on update)
    G = build_from_extraction(extraction)
    if update and code_only_update is False and (out_dir / "graph.json").exists():
        old_G, old_data = load_graph_file(out_dir / "graph.json")
        from .analyze import graph_diff

        diff = graph_diff(old_G, G)
        say(f"graph diff vs previous: {diff['summary']}")
        merged = Graph(directed=old_G.is_directed() or G.is_directed())
        for nid, nd in old_G.nodes_data():
            merged.add_node(nid, **nd)
        for u, v in old_G.edges_view():
            merged.add_edge(u, v, keep_existing=True, **(old_G.get_edge_data(u, v, {}) or {}))
        for nid, nd in G.nodes_data():
            merged.add_node(nid, **nd)
        for u, v in G.edges_view():
            merged.add_edge(u, v, keep_existing=True, **(G.get_edge_data(u, v, {}) or {}))
        G = merged

    # -------------------------------------------------- cluster + analyze
    communities, cmeta = cluster(G, resolution=resolution, ambiguous_scale=ambiguous_scale)
    cohesion = score_all(G, communities)
    labels = label_communities_by_hub(G, communities)
    mod = modularity(G, {n: c for c, ms in communities.items() for n in ms})
    gods = god_nodes(G, top_n=0)
    pr_ranks = god_nodes(G, top_n=0, by="pagerank")
    if exclude_hubs > 0:
        # suppress the N most-connected "utility super-hubs" from god-node
        # rankings so subsystem-level structure is visible (graphify parity)
        by_deg = sorted(G.degree_map().items(), key=lambda kv: -kv[1])[:exclude_hubs]
        suppressed = {nid for nid, _ in by_deg}
        gods = [g for g in gods if g["id"] not in suppressed]
        pr_ranks = [g for g in pr_ranks if g["id"] not in suppressed]
        say(f"god-node rankings: suppressed {len(suppressed)} super-hub(s) (--exclude-hubs {exclude_hubs})")
    surprises = surprising_connections(G, communities, top_n=0)
    questions = suggest_questions(G, communities, labels)
    cycles = find_cycles(G, limit=200)
    bridges, articulation = bridges_and_articulation(G)
    isolated = locate_isolated(G, top_n=0)
    say(
        f"graph: {G.number_of_nodes():,} nodes · {G.number_of_edges():,} edges · "
        f"{len(communities)} communities (modularity {mod:.3f}, method {cmeta.get('method')})"
    )

    # -------------------------------------------------- export
    links_stat = summarize_links(G)
    meta = {
        "detection": {k: detection.get(k) for k in ("total_files", "total_words", "warning", "scan_root")},
        "analysis": {
            "modularity": mod,
            "method": cmeta.get("method"),
            "cohesion": cohesion,
            "cycles": len(cycles),
            "bridges": len(bridges),
            "articulation": len(articulation),
            "isolated": len(isolated),
        },
        "confidence_profile": confidence_profile(G),
        "resolutions": extraction["resolutions"],
        "corpus_sha": None,
        "built_at": dt.datetime.now(dt.UTC).isoformat(),
        "nodemonk_version": __version__,
        "schema_version": detection.get("detector_version", __version__),
    }
    payload = to_json(G, communities, labels, out_dir / "graph.json", meta=meta)
    say("wrote graph.json")
    write_viz_html(G, communities, labels, out_dir / "graph.html", top_pagerank=_pr_map(pr_ranks), cohesion=cohesion)
    say("wrote graph.html (open in any browser - works up to any node count)")
    if svg:
        to_svg(G, communities, labels, out_dir / "graph.svg")
        say("wrote graph.svg")
    if graphml:
        to_graphml(G, out_dir / "graph.graphml")
        say("wrote graph.graphml")
    if cypher:
        to_cypher(G, out_dir / "cypher.txt")
        say("wrote cypher.txt - import: cypher-shell < nodemonk-out/cypher.txt")
    if dot:
        to_dot(G, out_dir / "graph.dot")
        say("wrote graph.dot")
    if obsidian:
        n = to_obsidian(G, communities, labels, out_dir / "obsidian", cohesion=cohesion)
        say(f"obsidian vault: {n} community notes in {out_dir}/obsidian/")
    if wiki:
        wdir = to_wiki(G, communities, labels, out_dir / "wiki", cohesion=cohesion)
        say(f"wiki: {wdir}/index.md + one article per community")
    if callflow:
        to_callflow_html(G, communities, labels, out_dir / "callflow.html")
        say("wrote callflow.html (Mermaid community call flow)")

    tokens = {"input": extraction.get("input_tokens", 0), "output": extraction.get("output_tokens", 0)}
    report = generate_report(
        G, communities, cohesion, labels, gods, surprises, detection,
        tokens, str(root), suggested_questions=questions,
        metrics={
            "modularity": mod,
            "modularity_str": f"{mod:.3f}",
            "connectivity": links_stat,
            "resolutions": extraction["resolutions"],
            "bridges": len(bridges),
            "articulation": len(articulation),
            "cycles": len(cycles),
            "isolated": len(isolated),
        },
    )
    atomic_write(out_dir / "GRAPH_REPORT.md", report)
    say("wrote GRAPH_REPORT.md")

    # -------------------------------------------------- bookkeeping
    manifest = detection.get("files") or {}
    save_manifest(out_dir, manifest)
    cost = _load_cost(out_dir)
    cost["runs"].append({
        "when": dt.datetime.now(dt.UTC).isoformat(),
        "files": detection["total_files"],
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "input_tokens": tokens["input"],
        "output_tokens": tokens["output"],
    })
    _save_cost(out_dir, cost)

    from .benchmark import run_benchmark

    bench = run_benchmark(out_dir / "graph.json", corpus_words=detection["total_words"])

    return {
        "out_dir": str(out_dir),
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "communities": len(communities),
        "modularity": round(mod, 4),
        "cycles": len(cycles),
        "bridges": len(bridges),
        "articulation": len(articulation),
        "isolated": len(isolated),
        "benchmark": bench,
        "questions": [q["question"] for q in questions],
        "labels": labels,
    }


def _pr_map(pr_rows: list[dict[str, Any]]) -> dict[str, float]:
    return {r["id"]: float(r["pagerank"]) for r in pr_rows if r.get("pagerank")}


def summarize_links(G: Graph) -> str:
    stats = global_stats(G)
    return (
        f"density {stats.get('edge_density', 0):.3%}, avg degree {stats.get('avg_degree', 0)}, "
        f"max degree {stats.get('max_degree', 0)}, self-loops {stats.get('self_loops', 0)}"
    )


def _load_cost(out_dir: Path) -> dict[str, Any]:
    p = out_dir / COST_FILE
    if p.exists():
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    return {"runs": []}


def _save_cost(out_dir: Path, cost: dict[str, Any]) -> None:
    p = out_dir / COST_FILE
    p.write_text(json.dumps(cost, indent=1), encoding="utf-8")


def cluster_only(out_dir: Path) -> dict[str, Any]:
    """Re-run clustering + analysis on an existing graph.json."""
    G, data = load_graph_file(out_dir / "graph.json")
    if G is None:
        return {"error": "graph.json missing"}
    communities, cmeta = cluster(G)
    cohesion = score_all(G, communities)
    labels = label_communities_by_hub(G, communities)
    comm_map = {n: c for c, ms in communities.items() for n in ms}
    mod = modularity(G, comm_map)
    gods = god_nodes(G, top_n=0)
    surp = surprising_connections(G, communities, top_n=0)
    questions = suggest_questions(G, communities, labels)
    prev_comms = {int(k): v for k, v in (data.get("communities") or {}).items()}
    if prev_comms:
        communities = _stable_remap(communities, prev_comms)
        cohesion = score_all(G, communities)
    detection = data.get("detection") or {}
    report = generate_report(
        G, communities, cohesion, labels, gods, surp, detection,
        {"input": 0, "output": 0}, detection.get("scan_root", "."),
        suggested_questions=questions,
        metrics={"modularity": mod, "modularity_str": f"{mod:.3f}", "resolutions": data.get("resolutions") or {}},
    )
    atomic_write(out_dir / "GRAPH_REPORT.md", report)
    to_json(G, communities, labels, out_dir / "graph.json", meta={
        **{k: v for k, v in data.items() if k in ("detection", "analysis", "confidence_profile", "resolutions")},
    })
    from .viz import write_viz_html as _viz

    _viz(G, communities, labels, out_dir / "graph.html")
    return {"communities": len(communities), "modularity": round(mod, 4), "nodes": G.number_of_nodes(), "edges": G.number_of_edges()}


def _stable_remap(communities: dict[int, list[str]], previous: dict[int, list[str]]) -> dict[int, list[str]]:
    """Minimize community-id churn by matching new comms to previous sets."""
    from .cluster import remap_communities_to_previous

    prev_node_comm = {n: c for c, ms in previous.items() for n in ms}
    return remap_communities_to_previous(communities, prev_node_comm)
