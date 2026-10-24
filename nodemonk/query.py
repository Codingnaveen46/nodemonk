"""nodemonk.query - the unlimited query surface over the persistent graph.

Design rule: no answer budget truncation by default.  graphify clamps query
output at ~2000 tokens; nodemonk never clamps unless --limit/--budget is set
explicitly (limit=0 = unlimited).
"""

from __future__ import annotations

import heapq
import re
from collections import deque
from typing import Any

from .graph import Graph

_TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]*")


def _tokens(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RE.findall(text or "")]


def search_nodes(
    G: Graph,
    terms: list[str],
    *,
    kind: str | None = None,
    community: list[int] | None = None,
    file_glob: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    """Score every node's label/docstring/source against the terms. Precise, no LLM."""
    terms_l = [t.lower() for t in terms if t]
    file_re = re.compile(file_glob) if file_glob else None
    matches: list[tuple[float, str]] = []
    for nid, nd in G.nodes_data():
        if kind and nd.get("file_type") != kind:
            continue
        if file_re and file_re.search(str(nd.get("source_file", ""))) is None:
            continue
        if community:
            cids = set(community)
            if nd.get("community") not in cids:
                continue
        label = str(nd.get("label", "")).lower()
        label_tokens = set(_tokens(label))
        score = 0.0
        for t in terms_l:
            if t == label or t in label_tokens:
                score += 5.0
            elif any(t in tok for tok in label_tokens):
                score += 2.5
            elif t in label:
                score += 1.5
            if t in str(nd.get("source_file", "")).lower():
                score += 1.0
            if t in str(nd.get("docstring", "")).lower():
                score += 0.5
        if score > 0:
            matches.append((score + G.degree(nid) * 0.01, nid))
    matches.sort(key=lambda pair: (-pair[0], pair[1]))
    if limit > 0:
        matches = matches[:limit]
    return [{"id": nid, "score": round(s, 3), **G.get_node(nid, {})} for s, nid in matches]


def resolve_start_nodes(G: Graph, question: str, max_starts: int = 3) -> list[str]:
    hits = search_nodes(G, _tokens(question), limit=max_starts)
    # require every hit to meaningfully match at least the leading terms
    return [h["id"] for h in hits if h["score"] > 1.0]


def bfs_subgraph(G: Graph, starts: list[str], depth: int = 3, limit: int = 0) -> dict[str, Any]:
    frontier = list(dict.fromkeys(starts))
    visited = set(frontier)
    edges_seen: set[tuple[str, str]] = set()
    levels = {n: 0 for n in frontier}
    for d in range(1, depth + 1):
        next_frontier: list[str] = []
        for u in frontier:
            for v in G.nbrs(u):
                edges_seen.add((u, v) if G.is_directed() or u <= v else (v, u))
                if v not in visited:
                    visited.add(v)
                    levels[v] = d
                    next_frontier.append(v)
        if limit and len(visited) >= limit:
            break
        frontier = next_frontier
        if not frontier:
            break
    sub_edges = [(u, v, G.get_edge_data(u, v, {})) for u, v in edges_seen]
    sub_edges.sort()
    return {"nodes": sorted(visited), "edges": sub_edges, "levels": levels}


def dfs_subgraph(G: Graph, starts: list[str], depth: int = 6, limit: int = 0) -> dict[str, Any]:
    visited: set[str] = set()
    edges_seen: set[tuple[str, str]] = set()
    for start in starts:
        if start in visited:
            continue
        stack = [(start, 0)]
        while stack:
            node, d = stack.pop()
            if node in visited or d > depth:
                continue
            visited.add(node)
            if limit and len(visited) >= limit:
                return {"nodes": sorted(visited), "edges": sorted(edges_seen), "levels": {}}
            nbrs = sorted(G.nbrs(node))
            for v in nbrs:
                edges_seen.add((node, v) if G.is_directed() or node <= v else (v, node))
                if v not in visited:
                    stack.append((v, d + 1))
    return {"nodes": sorted(visited), "edges": sorted(edges_seen), "levels": {}}


def ego_network(G: Graph, node: str, depth: int = 2, limit: int = 0) -> dict[str, Any]:
    return bfs_subgraph(G, [node], depth=depth, limit=limit)


def path_between(G: Graph, a: str, b: str, weighted: bool = False) -> dict[str, Any]:
    """Bidirectional search: BFS (unweighted) or Dijkstra (weighted)."""
    if not G.has_node(a) or not G.has_node(b):
        return {"found": False, "path": [], "hops": 0, "message": "node not in graph"}
    if a == b:
        return {"found": True, "path": [a], "hops": 0}

    if weighted:
        # simple-Dijkstra on undirected collapsing of arcs
        dist: dict[str, float] = {a: 0.0}
        prev: dict[str, str] = {}
        pq = [(0.0, a)]
        done: set[str] = set()
        while pq:
            d, u = heapq.heappop(pq)
            if u in done:
                continue
            done.add(u)
            if u == b:
                break
            for v in G.nbrs(u):
                if v == u:
                    continue
                w = float((G.get_edge_data(u, v, {}) or {}).get("weight", 1.0) or 1.0)
                nd = d + w
                if v not in dist or nd < dist[v]:
                    dist[v] = nd
                    prev[v] = u
                    heapq.heappush(pq, (nd, v))
        if b not in dist:
            return {"found": False, "path": [], "hops": 0, "message": "no weighted path"}
        path = [b]
        while path[-1] != a:
            path.append(prev[path[-1]])
        path.reverse()
        return {"found": True, "path": path, "hops": len(path) - 1, "cost": dist[b]}

    # bidirectional BFS: alternate expansions; on overlap assemble
    # a-side chain via the expanding node u and b-side chain from the hit v.
    front_a, front_b = {a: None}, {b: None}
    seen_a, seen_b = {a}, {b}
    queues = deque([a]), deque([b])
    turn_a = True

    def _chain(front: dict[str, str | None], node: str) -> list[str]:
        leg = [node]
        p = node
        while p in front and front[p] is not None:
            p = front[p]  # type: ignore[index assignment]
            leg.append(p)
        return leg

    while front_a and front_b:
        our_queue = queues[0] if turn_a else queues[1]
        for _ in range(len(our_queue)):
            u = our_queue.popleft()
            front_ours = front_a if turn_a else front_b
            seen_ours = seen_a if turn_a else seen_b
            other_front = front_b if turn_a else front_a
            other_seen = seen_b if turn_a else seen_a
            for v in G.nbrs(u):
                matched = v in other_seen
                if not matched:
                    if v not in seen_ours:
                        seen_ours.add(v)
                        front_ours[v] = u
                        our_queue.append(v)
                        continue
                    # already ours from an earlier level; not a shortcut candidate
                    continue
                our_leg = _chain(front_ours, u)  # u .. a
                other_leg = _chain(other_front, v)  # v .. other source
                path = list(reversed(our_leg)) + other_leg
                return {"found": True, "path": path, "hops": len(path) - 1}
        turn_a = not turn_a
    return {"found": False, "path": [], "hops": 0, "message": "no path"}


def shortest_path_all(G: Graph, source: str, limit: int = 0) -> dict[str, dict[str, Any]]:
    """Full single-source distances (BFS), unlimited by default."""
    if not G.has_node(source):
        return {}
    dist = {source: 0}
    parent: dict[str, str] = {}
    q = deque([source])
    while q:
        u = q.popleft()
        for v in G.nbrs(u):
            if v == u or v in dist:
                continue
            dist[v] = dist[u] + 1
            parent[v] = u
            q.append(v)
    out = {u: {"dist": d, "via": parent.get(u)} for u, d in dist.items()}
    if limit:
        out = dict(list(out.items())[:limit])
    return out


def explain_node(G: Graph, node: str) -> dict[str, Any]:
    if not G.has_node(node):
        return {"error": f"node {node!r} not in graph"}
    nd = dict(G.get_node(node, {}) or {})
    neighbors: list[dict[str, Any]] = []
    incoming: list[dict[str, Any]] = []
    outgoing: list[dict[str, Any]] = []

    for v, d in G.nbrs(node).items():
        d = d or {}
        v_node = G.get_node(v, {}) or {}
        v_label = v_node.get("label") or v
        v_file = v_node.get("source_file") or v_node.get("file")
        v_kind = v_node.get("kind")
        rel = d.get("relation", "links")
        conf = d.get("confidence", "EXTRACTED")
        weight = d.get("weight", 1.0)

        entry = {
            "id": v,
            "to": v,
            "node": v,
            "label": v_label,
            "relation": rel,
            "confidence": conf,
            "weight": weight,
            "file": v_file,
            "kind": v_kind,
        }
        neighbors.append(entry)

        src = d.get("_src")
        tgt = d.get("_tgt")
        if src == node:
            outgoing.append(entry)
        elif tgt == node:
            incoming.append(entry)
        else:
            outgoing.append(entry)

    neighbors.sort(key=lambda r: (-(r["weight"] or 0.0), str(r["label"])))
    incoming.sort(key=lambda r: (-(r["weight"] or 0.0), str(r["label"])))
    outgoing.sort(key=lambda r: (-(r["weight"] or 0.0), str(r["label"])))

    return {
        "id": node,
        **{k: v for k, v in nd.items()},
        "degree": G.degree(node),
        "neighbors": neighbors,
        "incoming": incoming,
        "outgoing": outgoing,
    }


def neighbor_filter(
    G: Graph,
    node: str,
    *,
    relation: str | None = None,
    direction: str = "any",
    confidence: str | None = None,
) -> list[dict[str, Any]]:
    outs: list[dict[str, Any]] = []
    for v, d in G.nbrs(node).items():
        d = d or {}
        if relation and d.get("relation") != relation:
            continue
        if confidence and d.get("confidence") != confidence:
            continue
        outs.append({"neighbor": v, **d})
    return outs


def community_profile(G: Graph, communities: dict[int, list[str]], cid: int) -> dict[str, Any]:
    members = communities.get(cid, [])
    member_set = set(members)
    internal = sum(1 for u in members for v in G.nbrs(u) if v in member_set) // 2
    density = (internal / (len(members) * (len(members) - 1) / 2)) if len(members) > 1 else 1.0
    outs: list[dict[str, Any]] = []
    for u in members:
        for v in G.nbrs(u):
            if v not in member_set:
                outs.append((u, v))
    from .cluster import cohesion_score  # local import to avoid cycle
    return {
        "id": cid,
        "size": len(members),
        "internal_edges": internal,
        "density": density,
        "cohesion": cohesion_score(G, members),
        "out_degree": sum(1 for _ in outs),
    }


def global_stats(G: Graph) -> dict[str, Any]:
    n = G.number_of_nodes()
    e = G.number_of_edges()
    if n == 0:
        return {"nodes": 0, "edges": 0}
    degs = sorted(G.degree_map().values())
    mean = sum(degs) / n
    median = degs[n // 2]
    return {
        "nodes": n,
        "edges": e,
        "avg_degree": round(mean, 3),
        "median_degree": median,
        "max_degree": degs[-1],
        "self_loops": sum(1 for u in G.nodes() if u in G.nbrs(u)),
        "edge_density": e / (n * (n - 1) / 2) if n > 1 else 0.0,
    }
