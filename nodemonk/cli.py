"""nodemonk.cli - the command surface.

Everything queryable is unlimited by default: pass --limit N only when you
want a cap. 0 means "all" everywhere.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from . import __app_name__, __version__
from .graph import Graph
from .export import load_graph_file

DEFAULT_OUT_DIR_PARAM = "nodemonk-out"


def out_dir_for(root: Path) -> Path:
    return root / DEFAULT_OUT_DIR_PARAM


def _load(args) -> tuple[Graph, dict[str, Any]]:  # noqa: ANN001 (CLI-internal)
    root = Path(rng := getattr(args, "root", ".") or ".").resolve()
    out_dir = Path(getattr(args, "out_dir", "") or out_dir_for(root))
    path = getattr(args, "graph", None) if getattr(args, "graph", None) else out_dir / "graph.json"
    path = Path(path)
    if not path.exists():
        raise SystemExit(
            f"ERROR: no graph at {path}.\nRun `{__app_name__} build <path>` first, or pass --graph."
        )
    data = json.loads(path.read_text(encoding="utf-8"))
    return Graph.from_node_link(data), data


def _labels(data: dict[str, Any]) -> dict[int, str]:
    return {int(k): v for k, v in (data.get("community_labels") or {}).items()}


def _communities(data: dict[str, Any]) -> dict[int, list[str]]:
    return {int(k): v for k, v in (data.get("communities") or {}).items()}


def _label(G: Graph, nid: str) -> str:
    nd = G.get_node(nid, {}) or {}
    return str(nd.get("label") or nid)


# --------------------------------------------------------------------- #
# subcommand handlers

def cmd_build(args) -> None:  # noqa: ANN001
    from .pipeline import run_pipeline

    root = Path(args.root).resolve()
    summary = run_pipeline(
        root,
        out_dir=Path(args.out_dir) if args.out_dir else None,
        update=args.update,
        code_only_update=args.code_only,
        resolution=args.resolution,
        ambiguous_scale=args.ambiguous_scale,
        workers=args.workers,
        max_files=args.max_files,
        quiet=args.quiet,
        html=not args.no_viz,
        svg=args.svg,
        graphml=args.graphml,
        cypher=args.cypher,
        dot=args.dot,
        obsidian=args.obsidian,
    )
    if "error" in summary:
        print(summary["error"], file=sys.stderr)
        raise SystemExit(1)
    bench = summary.get("benchmark") or {}
    print()
    print(
        f"graph complete. outputs in {summary['out_dir']}/\n"
        f"  graph.html        - interactive graph (any node count), open in browser\n"
        f"  GRAPH_REPORT.md   - honest audit + highlights\n"
        f"  graph.json        - the persistent graph\n"
    )
    print(f"stats: {summary['nodes']:,} nodes · {summary['edges']:,} edges · {summary['communities']} communities "
          f"(modularity {summary.get('modularity', 0) if summary.get('modularity') is not None else 0})")
    if bench:
        from .benchmark import print_benchmark

        print(print_benchmark(bench))
    questions = summary.get("questions") or []
    labels = summary.get("labels") or {}
    if questions:
        print("\nFirst questions worth tracing:")
        for q in questions[:3]:
            print(f"  - {q}")


def cmd_query(args) -> None:  # noqa: ANN001
    from .query import bfs_subgraph, dfs_subgraph, resolve_start_nodes, search_nodes

    G, data = _load(args)
    starts = resolve_start_nodes(G, args.question, max_starts=3)
    if not starts:
        hits = search_nodes(G, [t for t in args.question.split() if len(t) > 2], limit=5)
        if hits:
            print("no graph node matched strongly. closest candidates:")
            for h in hits:
                print(f"  {h['id']}  ({h.get('label')})")
        else:
            print("no match in graph for that question")
        return
    mode = args.mode
    depth = args.depth or (3 if mode == "bfs" else 6)
    sub = bfs_subgraph(G, starts, depth=depth, limit=args.limit if args.limit else 0) if mode == "bfs" else dfs_subgraph(G, starts, depth=depth, limit=args.limit if args.limit else 0)
    node_comm: dict[str, int] = {}
    for cid, ms in _communities(data).items():
        for n in ms:
            node_comm[n] = cid
    labels = _labels(data)
    print(f"traversal: {mode.upper()} · seeds: {[_label(G, s) for s in starts]} · {len(sub['nodes']):,} nodes · depth {depth}")
    for nid in sub["nodes"]:
        nd = G.get_node(nid, {}) or {}
        dep = sub.get("levels", {}).get(nid)
        com = node_comm.get(nid)
        c_label = labels.get(com, com) if com is not None else None
        head = f"{'  ' * (dep or 0)}• {nd.get('label', nid)}"
        bits = [str(x) for x in (nd.get("source_file"), f"[{c_label}]" if c_label else "", f"L{nd.get('source_location')}" if nd.get('source_location') else "") if x]
        if bits:
            head += "  · " + " ".join(bits)
        print(head)
    if args.limit and len(sub["edges"]) > args.limit:
        print(f"  (+ {len(sub['edges']) - args.limit:,} edges not shown; --limit 0 = unlimited)")
    else:
        for a, b, d in sub["edges"][: (args.limit or len(sub['edges']))]:
            dd = d if isinstance(d, dict) else {}
            print(f"  {_label(G, a)} --{dd.get('relation', '')} ({dd.get('confidence', '')})--> {_label(G, b)}")


def cmd_path(args) -> None:  # noqa: ANN001
    from .query import path_between, search_nodes

    G, _ = _load(args)
    a = _best_node(G, args.a)
    b = _best_node(G, args.b)
    if not a or not b:
        raise SystemExit("could not resolve both endpoints in the graph")
    res = path_between(G, a, b, weighted=args.weighted)
    if not res.get("found"):
        print(f"no path between {_label(G, a)!r} and {_label(G, b)!r} ({res.get('message', '')})")
        raise SystemExit(0)
    path = res["path"]
    print(f"shortest path ({res['hops']} hops{f', cost {res['cost']}' if res.get('cost') is not None else ''}):")
    for i, nid in enumerate(path):
        if i < len(path) - 1:
            d = G.get_edge_data(nid, path[i + 1], {}) or {}
            print(f"  {G.get_node(nid, {}).get('label', nid)} --{d.get('relation', '')} [{d.get('confidence', '')}]-->")
        else:
            print(f"  {G.get_node(nid, {}).get('label', nid)}")


def _best_node(G: Graph, term: str) -> str | None:
    from .query import search_nodes

    if term in G:
        return term
    hits = search_nodes(G, [term], limit=1)
    return hits[0]["id"] if hits else None


def cmd_explain(args) -> None:  # noqa: ANN001
    from .query import explain_node

    G, data = _load(args)
    nid = _best_node(G, args.node)
    if nid is None:
        raise SystemExit(f"no node matching {args.node!r}")
    info = explain_node(G, nid)
    labels = _labels(data)
    comms = _communities(data)
    com = None
    for cid, ms in comms.items():
        if nid in ms:
            com = cid
            break
    print(f"node: {info.get('label', nid)}")
    if info.get("source_file"):
        print(f"  source: {info['source_file']} {info.get('source_location', '')}")
    print(f"  type: {info.get('file_type', '')}")
    print(f"  degree: {info.get('degree', 0)}")
    if com is not None:
        print(f"  community: {com} ({labels.get(com, 'n/a')})")
    doc = info.get("docstring")
    if doc:
        print(f"  docstring: {doc[:300]}")
    print("\nconnections:")
    for ne in info.get("neighbors", []):
        print(f"  --{ne.get('relation', '')}--> {G.get_node(ne['to'], {}).get('label', ne['to'])} [{ne.get('confidence', '')}]")


def cmd_search(args) -> None:  # noqa: ANN001
    from .query import search_nodes

    G, _ = _load(args)
    hits = search_nodes(
        G, args.terms,
        kind=args.kind if args.kind else None,
        file_glob=args.file if args.file else None,
        community=[int(x) for x in (args.community or "").split(",") if x] or None,
        limit=args.limit,
    )
    print(f"{len(hits)} hit(s) (unlimited unless --limit set):")
    for h in hits:
        print(f"  [{h['score']:6.2f}] {h.get('label', h['id'])}  · {h.get('file_type', '')} · {h.get('source_file', '')}")


def cmd_top(args) -> None:  # noqa: ANN001
    from .analyze import god_nodes

    G, data = _load(args)
    rows = god_nodes(G, top_n=args.limit if args.limit else 0, by=args.by)
    comms = _communities(data)
    node_comm = {n: c for c, ms in comms.items() for n in ms}
    labels = _labels(data)
    valk = args.by if args.by != "in" else "in"
    print(f"top {len(rows):,} nodes by {args.by}:")
    for r in rows:
        c = node_comm.get(r["id"])
        scent = f" ({labels.get(c, c)})" if c is not None else ""
        val = r.get(valk, r.get('degree', 0)) if valk in r else r.get("degree", 0)
        print(f"  {r['label']}: {val}s{scent}  · {r.get('source_file')}")


def cmd_stats(args) -> None:  # noqa: ANN001
    from .query import global_stats
    from .analyze import confidence_profile

    G, data = _load(args)
    st = global_stats(G)
    cp = confidence_profile(G)
    print("graph stats:")
    for k, v in st.items():
        print(f"  {k}: {v:,}" if isinstance(v, int) else f"  {k}: {v}")
    print("confidence profile:", {k: v for k, v in cp.items() if v})
    comm = _communities(data)
    print(f"communities: {len(comm)}")



def cmd_community(args) -> None:  # noqa: ANN001
    from .cluster import cohesion_score

    G, data = _load(args)
    comms = _communities(data)
    labels = _labels(data)
    if args.list:
        for cid in sorted(comms):
            print(f"  {cid:>4}  {labels.get(cid, f'Community {cid}')}  ({len(comms[cid]):,} nodes, cohesion {cohesion_score(G, comms[cid]) * 100:.1f}%)")
        return
    cid = args.id
    if cid not in comms:
        raise SystemExit(f"community {cid} not found")
    members = comms[cid]
    ms = set(members)
    out = sorted({v for m in members for v in G.nbrs(m) if v not in ms})
    print(f"community {cid} - {labels.get(cid, '')} ({len(members):,} nodes, cohesion {cohesion_score(G, members) * 100:.1f}%)")
    print("members (all):")
    for m in sorted(members, key=lambda n: -G.degree(n)):
        print(f"  {G.get_node(m, {}).get('label', m)} · {G.get_node(m, {}).get('file_type', '')} · {G.get_node(m, {}).get('source_file', '')}")
    if out:
        print(f"out-reach ({len(out):,}):")
        for o in out:
            print(f"  → {G.get_node(o, {}).get('label', o)}")


def cmd_cycles(args) -> None:  # noqa: ANN001
    from .analyze import find_cycles

    G, _ = _load(args)
    cyc = find_cycles(G, limit=args.limit if args.limit else 0)
    print(f"{len(cyc)} cycle(s):")
    for c in cyc:
        print("  " + " -> ".join(G.get_node(n, {}).get("label", n) for n in c) + f" [{c[0]}]")


def cmd_bridges(args) -> None:  # noqa: ANN001
    from .analyze import bridges_and_articulation

    G, _ = _load(args)
    br, art = bridges_and_articulation(G)
    print(f"bridges ({len(br):,}):")
    for u, v in br[: (args.limit or len(br))]:
        print(f"  {_label(G, u)} — {_label(G, v)}")
    if art:
        print(f"articulation points ({len(art):,}):")
        for a2 in art[: (args.limit or len(art))]:
            print(f"  {_label(G, a2)}")


def cmd_isolated(args) -> None:  # noqa: ANN001
    from .analyze import locate_isolated

    G, _ = _load(args)
    iso = locate_isolated(G, top_n=args.limit if args.limit else 0)
    print(f"{len(iso):,} isolated nodes:")
    for n in iso[: (args.limit or len(iso))]:
        print(f"  {_label(G, n)}")


def cmd_cluster_only(args) -> None:  # noqa: ANN001
    from .pipeline import cluster_only

    root = Path(args.root).resolve()
    out = Path(args.out_dir) if args.out_dir else out_dir_for(root)
    res = cluster_only(out)
    if "error" in res:
        print(res["error"], file=sys.stderr)
        raise SystemExit(1)
    print(f"re-clustered: {res}")


def cmd_serve(args) -> None:  # noqa: ANN001
    from .serve import serve_http

    graph = Path(args.graph) if args.graph else out_dir_for(Path(args.root).resolve()) / "graph.json"
    serve_http(str(graph), host=args.host, port=args.port)


def cmd_mcp(args) -> None:  # noqa: ANN001
    from .mcp import serve

    graph = Path(args.graph) if args.graph else out_dir_for(Path(args.root).resolve()) / "graph.json"
    serve(str(graph))


def cmd_watch(args) -> None:  # noqa: ANN001
    from .watch import watch

    watch(Path(args.root).resolve(), debounce=args.debounce)


def cmd_add(args) -> None:  # noqa: ANN001
    from .ingest import ingest

    root = Path(args.root).resolve()
    target = root / "raw"
    try:
        out = ingest(args.url, target, author=args.author, contributor=args.contributor)
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
    print(f"saved to {out}")
    print(f"run `nodemonk build {root} --update` to fold it into the graph")


def cmd_hook(args) -> None:  # noqa: ANN001
    from .hook import install, uninstall, status

    repo = Path(args.root).resolve()
    if args.action == "install":
        print(install(repo))
    elif args.action == "uninstall":
        print(uninstall(repo))
    else:
        print(status(repo))


def cmd_skill(args) -> None:  # noqa: ANN001
    """Install a /command + agent-file section so assistants can use nodemonk natively."""
    repo = Path(args.root).resolve()
    from .hook import SKILL_MARKDOWN_MARKERS

    if args.action == "install":
        path = repo / "AGENTS.md" if (repo / "AGENTS.md").exists() else repo / "CLAUDE.md"
        content = path.read_text(encoding="utf-8") if path.exists() else f"# {repo.name}\n"
        if MARKER in content:
            print("already installed")
            return
        content = content.rstrip() + "\n\n" + SKILL_MARKDOWN_MARKERS.format(ROOT=str(repo), OUT=str(out_dir_for(repo))) + "\n"
        path.write_text(content, encoding="utf-8")
        print(f"nodemonk skill installed in {path}")
    else:
        path = repo / "AGENTS.md" if (repo / "AGENTS.md").exists() else repo / "CLAUDE.md"
        if not path.exists():
            print("nothing to remove")
            return
        content = path.read_text(encoding="utf-8")
        start = content.find(MARKER)
        if start < 0:
            print("nothing to remove")
            return
        end = content.find(MARKER_END, start)
        if end < 0:
            print("marker found but unclosed; removing from the marker onward")
            content = content[:start].rstrip() + "\n"
        else:
            content = (content[:start].rstrip() + "\n" if start > 0 else "") + content[end + len(MARKER_END):].strip("\n")
        path.write_text(content, encoding="utf-8")
        print("nodemonk skill removed")


MARKER = "<!-- nodemonk-skill -->"
MARKER_END = "<!-- /nodemonk-skill -->"


def cmd_bench(args) -> None:  # noqa: ANN001
    from .benchmark import run_benchmark, print_benchmark

    graph = Path(args.graph) if args.graph else out_dir_for(Path(args.root).resolve()) / "graph.json"
    data = json.loads(graph.read_text(encoding="utf-8"))
    words = (data.get("detection") or {}).get("total_words")
    res = run_benchmark(graph, corpus_words=words)
    print(print_benchmark(res))


# --------------------------------------------------------------------- #
# argparser

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="nodemonk",
        description="See everything. Ask anything - any corpus into a persistent, queryable knowledge graph.",
        epilog="everything stays on your machine. nothing is capped: use --limit 0 (default) everywhere.",
    )
    p.add_argument("--version", action="version", version=f"{__app_name__} {__version__}")
    sub = p.add_subparsers(dest="cmd", required=True)

    def add_graph_args(sp) -> None:  # noqa: ANN001
        sp.add_argument("--root", default=".", help="project root (out dir resolves here)")
        sp.add_argument("--graph", default=None, help="explicit graph.json path")
        sp.add_argument("--out-dir", default=None, help="override output directory")

    build_sp = sub.add_parser("build", help="build (or re-scan) the knowledge graph")
    build_sp.add_argument("root", nargs="?", default=".", help="corpus root")
    build_sp.add_argument("--out-dir", default=None, help="override output directory (default: <root>/nodemonk-out)")
    build_sp.add_argument("--update", action="store_true", help="incremental: only new/changed files re-extract (cache hashes all)")
    build_sp.add_argument("--code-only", action="store_true", help="restrict update to code files (deterministic, free)")
    build_sp.add_argument("--workers", type=int, default=None, help="extraction worker processes (default: auto)")
    build_sp.add_argument("--max-files", type=int, default=0, help="0 = unlimited (safety valve only)")
    build_sp.add_argument("--resolution", type=float, default=1.0, help="community resolution (>1 = more smaller communities)")
    build_sp.add_argument("--ambiguous-scale", type=float, default=0.5, help="weight multiplier for AMBIGUOUS edges while clustering (0 = drop)")
    build_sp.add_argument("--no-viz", action="store_true", help="skip graph.html")
    build_sp.add_argument("--svg", action="store_true")
    build_sp.add_argument("--graphml", action="store_true")
    build_sp.add_argument("--cypher", action="store_true", help="also emit cypher.txt for Neo4j")
    build_sp.add_argument("--dot", action="store_true")
    build_sp.add_argument("--obsidian", action="store_true", help="Obsidian vault (one note per community)")
    build_sp.add_argument("--quiet", action="store_true")
    build_sp.set_defaults(func=cmd_build)

    q_sp = sub.add_parser("query", help="BFS/DFS traversal answering a question - unlimited output")
    add_graph_args(q_sp)
    q_sp.add_argument("question")
    q_sp.add_argument("--dfs", action="store_const", dest="mode", const="dfs", default="bfs")
    q_sp.add_argument("--depth", type=int, default=0)
    q_sp.add_argument("--limit", type=int, default=0, help="0 = unlimited")
    q_sp.set_defaults(func=cmd_query)

    path_sp = sub.add_parser("path", help="shortest path between two concepts")
    add_graph_args(path_sp)
    path_sp.add_argument("a")
    path_sp.add_argument("b")
    path_sp.add_argument("--weighted", action="store_true", help="Dijkstra on edge weights instead of BFS")
    path_sp.set_defaults(func=cmd_path)

    exp = sub.add_parser("explain", help="explain one node: everything connected to it")
    add_graph_args(exp)
    exp.add_argument("node")
    exp.set_defaults(func=cmd_explain)

    s_sp = sub.add_parser("search", help="scored node search - unlimited")
    add_graph_args(s_sp)
    s_sp.add_argument("terms", nargs="+")
    s_sp.add_argument("--kind", default=None, help="filter file_type (code|document|data|paper|image|hyperedge)")
    s_sp.add_argument("--file", default=None, help="regex on source file path")
    s_sp.add_argument("--community", default=None, help="comma-separated community ids")
    s_sp.add_argument("--limit", type=int, default=50, help="0 = unlimited")
    s_sp.set_defaults(func=cmd_search)

    top_sp = sub.add_parser("top", help="best nodes by degree|pagerank")
    add_graph_args(top_sp)
    top_sp.add_argument("--by", default="degree", choices=["degree", "pagerank"])
    top_sp.add_argument("--limit", type=int, default=25, help="0 = all")
    top_sp.set_defaults(func=cmd_top)

    st = sub.add_parser("stats", help="graph statistics")
    add_graph_args(st)
    st.set_defaults(func=cmd_stats)

    com = sub.add_parser("community", help="inspect or list communities")
    add_graph_args(com)
    com.add_argument("id", nargs="?", type=int, default=None)
    com.add_argument("--list", action="store_true")
    com.set_defaults(func=cmd_community)

    cy = sub.add_parser("cycles", help="cycle detection (directed view)")
    add_graph_args(cy)
    cy.add_argument("--limit", type=int, default=20, help="0 = all")
    cy.set_defaults(func=cmd_cycles)

    br = sub.add_parser("bridges", help="bridge edges + articulation points")
    add_graph_args(br)
    br.add_argument("--limit", type=int, default=0, help="0 = all")
    br.set_defaults(func=cmd_bridges)

    iso = sub.add_parser("isolated", help="nodes with zero edges")
    add_graph_args(iso)
    iso.add_argument("--limit", type=int, default=0, help="0 = all")
    iso.set_defaults(func=cmd_isolated)

    cl = sub.add_parser("cluster-only", help="re-run clustering/analysis on the existing graph")
    cl.add_argument("root", nargs="?", default=".")
    cl.add_argument("--out-dir", default=None)
    cl.set_defaults(func=cmd_cluster_only)

    sv = sub.add_parser("serve", help="HTTP JSON API + tiny query console")
    add_graph_args(sv)
    sv.add_argument("--host", default="127.0.0.1")
    sv.add_argument("--port", type=int, default=7740)
    sv.set_defaults(func=cmd_serve)

    mc = sub.add_parser("mcp", help="start the stdio MCP server (agent access)")
    add_graph_args(mc)
    mc.set_defaults(func=cmd_mcp)

    wt = sub.add_parser("watch", help="watch the folder, rebuild on change (debounced)")
    wt.add_argument("root", nargs="?", default=".")
    wt.add_argument("--debounce", type=float, default=3.0)
    wt.set_defaults(func=cmd_watch)

    add = sub.add_parser("add", help="capture a URL into ./raw then re-update graph")
    add.add_argument("url")
    add.add_argument("--author", default=None)
    add.add_argument("--contributor", default=None)
    add.add_argument("root", nargs="?", default=".")
    add.set_defaults(func=cmd_add)

    hk = sub.add_parser("hook", help="git post-commit hook: install|uninstall|status")
    hk.add_argument("action", choices=["install", "uninstall", "status"])
    hk.add_argument("root", nargs="?", default=".")
    hk.set_defaults(func=cmd_hook)

    sk = sub.add_parser("skill", help="write nodemonk instructions into AGENTS.md/CLAUDE.md")
    sk.add_argument("action", choices=["install", "uninstall"])
    sk.add_argument("root", nargs="?", default=".")
    sk.set_defaults(func=cmd_skill)

    bn = sub.add_parser("bench", help="token compression benchmark for the built graph")
    add_graph_args(bn)
    bn.set_defaults(func=cmd_bench)

    return p


def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        args.func(args)
    except BrokenPipeError:
        raise SystemExit(0)


if __name__ == "__main__":
    main()
