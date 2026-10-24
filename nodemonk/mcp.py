"""nodemonk.mcp - stdio MCP server exposing the graph to any agent host.

Protocol: JSON-RPC 2.0 over stdin/stdout, one JSON object per line.
Tools (all unlimited): graph_stats, search, get_node, neighbors, query_graph,
shortest_path, god_nodes, pagerank_top, community, cycles, bridges.

Configure in claude_desktop_config.json (or any MCP host):
  {"mcpServers": {"nodemonk": {"command": "python3",
                              "args": ["-m", "nodemonk.mcp", "/path/nodemonk-out/graph.json"]}}}
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from .graph import Graph
from .query import (
    bfs_subgraph,
    dfs_subgraph,
    explain_node,
    global_stats,
    neighbor_filter,
    path_between,
    resolve_start_nodes,
    search_nodes,
)
from .cluster import cohesion_score

_PROTOCOL_VERSION = "2024-11-05"


def _tool(name: str, description: str) -> dict[str, Any]:
    return {"name": name, "description": description}


_TOOLS: list[dict[str, Any]] = [
    _tool("graph_stats", "Node/edge counts, degree profile, density, self-loops."),
    _tool("search", "Fuzzy search the graph (id/label/file/docstring). Args: terms[], kind?, file_glob?, limit?. nodemonk never truncates unless limit set."),
    _tool("get_node", "Full node payload. Args: id or label."),
    _tool("neighbors", "Adjacent nodes filtered by relation/confidence. Args: node, relation?, confidence?, direction?"),
    _tool("query_graph", "Traverse: mode=bfs|dfs from the best nodes matching a question. Args: question, mode?, depth?, limit?"),
    _tool("shortest_path", "Bidirectional BFS or weighted Dijkstra between two nodes. Args: a, b, weighted?"),
    _tool("god_nodes", "Highest impact nodes. Args: by=degree|pagerank, top_n (0=all)."),
    _tool("community", "One community: members + cohesion + out-reach. Args: id."),
    _tool("cycles", "Strongly-connected component cycles (directed view). Args: limit (0=all)."),
    _tool("bridges", "Bridge edges + articulation points."),
]

_cached: dict[str, Any] = {"path": None, "G": None, "communities": {}, "data": {}}


def load_state(path: str) -> None:
    if _cached["G"] is not None and _cached["path"] == str(path):
        return
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    G = Graph.from_node_link(data)
    _cached["path"] = str(path)
    _cached["G"] = G
    _cached["data"] = data
    _cached["communities"] = {int(k): v for k, v in (data.get("communities") or {}).items()}


def state() -> tuple[Graph, dict[str, Any]]:
    return _cached["G"], _cached["data"]


def label_of(G: Graph, nid: str) -> str:
    nd = G.get_node(nid, {}) or {}
    return str(nd.get("label") or nid)


def find_node(G: Graph, key: str) -> str | None:
    if G.has_node(key):
        return key
    hits = search_nodes(G, [str(key)], limit=1)
    if hits:
        return hits[0]["id"]
    return None


def call_tool(name: str, args: dict[str, Any]) -> dict[str, Any]:
    G, _data = state()
    if G is None:
        raise RuntimeError("no graph loaded")
    args = args or {}
    if name == "graph_stats":
        return global_stats(G)
    if name == "search":
        terms = args.get("terms") or ([args.get("query", "")] if args.get("query") else [])
        return {"nodes": search_nodes(
            G, terms,
            kind=args.get("kind"),
            community=args.get("community"),
            file_glob=args.get("file_glob"),
            limit=int(args.get("limit", 0) or 0),
        )}
    if name == "get_node":
        nid = find_node(G, str(args.get("id") or args.get("label") or ""))
        if nid is None:
            return {"error": f"node {args.get('id') or args.get('label')!r} not found"}
        return explain_node(G, nid)
    if name == "neighbors":
        nid = find_node(G, str(args.get("node") or ""))
        if nid is None:
            return {"error": "node not found"}
        return {"neighbors": neighbor_filter(G, nid, relation=args.get("relation"),
                                             direction=args.get("direction", "any"),
                                             confidence=args.get("confidence"))}
    if name == "query_graph":
        q = str(args.get("question") or "")
        starts = resolve_start_nodes(G, q, max_starts=3)
        if not starts:
            return {"error": f"no graph node matches {q!r}"}
        mode = str(args.get("mode") or "bfs").lower()
        depth = int(args.get("depth", 3 if mode == "bfs" else 6))
        limit = int(args.get("limit", 0) or 0)
        sub = bfs_subgraph(G, starts, depth=depth, limit=limit) if mode == "bfs" else dfs_subgraph(G, starts, depth=depth, limit=limit)
        return {
            "mode": mode,
            "starts": [{"id": s, "label": label_of(G, s)} for s in starts],
            "nodes": [
                {"id": n, "label": label_of(G, n), "depth": sub.get("levels", {}).get(n),
                 **(G.get_node(n, {}) or {})}
                for n in sub["nodes"]
            ],
            "edges": [
                {"source": a, "target": b, **({"relation": d.get("relation"), "confidence": d.get("confidence")} if isinstance(d, dict) else {})}
                for a, b, d in sub["edges"]
            ],
        }
    if name == "shortest_path":
        a = find_node(G, str(args.get("a") or ""))
        b = find_node(G, str(args.get("b") or ""))
        if a is None or b is None:
            return {"error": "one or both endpoints not found"}
        res = path_between(G, a, b, weighted=bool(args.get("weighted")))
        res["labels"] = [label_of(G, n) if G.has_node(n) else n for n in res.get("path", [])]
        return res
    if name == "god_nodes":
        from .analyze import god_nodes as _gods

        by = str(args.get("by", "degree"))
        top = int(args.get("top_n", 15))
        return {"gods": _gods(G, top_n=top, by="pagerank" if by == "pagerank" else "degree")}
    if name == "community":
        cid = int(args.get("id", 0))
        members = _cached["communities"].get(cid)
        if members is None:
            return {"error": f"community {cid} not found"}
        from .cluster import cohesion_score as _coh

        member_set = set(members)
        out_reach = sorted({v for m in members for v in G.nbrs(m) if v not in member_set})
        return {"id": cid, "members": members, "cohesion": _coh(G, members), "out_reach": out_reach}
    if name == "cycles":
        from .analyze import find_cycles

        lim = int(args.get("limit", 20))
        return {"cycles": find_cycles(G, limit=lim if lim > 0 else 0)}
    if name == "bridges":
        from .analyze import bridges_and_articulation

        br, art = bridges_and_articulation(G)
        return {"bridges": br[:200], "articulation": art[:200], "truncated": len(br) > 200 or len(art) > 200}
    return {"error": f"unknown tool {name}"}


def serve(graph_path: str) -> None:  # pragma: no cover (interactive loop)
    load_state(graph_path)

    def send(payload: dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    while True:
        line = sys.stdin.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            send({"jsonrpc": "2.0", "error": {"code": -32700, "message": "parse error"}, "id": None})
            continue
        method = req.get("method", "")
        rid = req.get("id")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": _PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "nodemonk", "version": _version()},
            }})
        elif method == "notifications/initialized":
            continue
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": rid, "result": {}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": rid, "result": {"tools": _TOOLS}})
        elif method == "tools/call":
            params = req.get("params") or {}
            name = params.get("name")
            try:
                result = call_tool(str(name), params.get("arguments") or {})
                send({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False)}],
                }})
            except Exception as exc:  # noqa: BLE001 (report, don't crash the host)
                send({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": json.dumps({"error": str(exc)})}],
                    "isError": True,
                }})
        elif method == "shutdown":
            send({"jsonrpc": "2.0", "id": rid, "result": {}})
            break
        else:
            send({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32601, "message": f"method not found: {method}"}})


def _version() -> str:
    from . import __version__

    return str(__version__)


if __name__ == "__main__":
    import sys as _sys

    if len(_sys.argv) < 2:
        _sys.stderr.write("usage: python -m nodemonk.mcp <graph.json>\n")
        raise SystemExit(1)
    serve(_sys.argv[1])
