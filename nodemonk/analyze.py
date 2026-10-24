"""nodemonk.analyze - every measurement the report and query live off.

All functions accept a nodemonk Graph. Algorithms implemented natively:
god nodes, PageRank, in-degree/out-degree hubs, bridges, articulation points,
import cycles (directed), surprise (cross-community edges), graph diff, and
suggested questions. No artificial top-N limit; callers choose `top_n=0`/all.
"""

from __future__ import annotations

from typing import Any, Iterable

from .graph import Graph


# --------------------------------------------------------------------- #
# basics

def god_nodes(G: Graph, top_n: int = 10, by: str = "degree") -> list[dict[str, Any]]:
    """Highest-impact nodes. by in {degree, pagerank, in, out}. top_n=0 -> all."""
    if by == "pagerank":
        pr = pagerank(G)
        rows = sorted(pr.items(), key=lambda kv: -kv[1])
        return [
            _god_row(G, nid, value, "pagerank") for nid, value in (rows if not top_n else rows[:top_n])
        ]
    degrees = G.degree_map()
    ranked = sorted(degrees.items(), key=lambda kv: (-kv[1], kv[0]))
    if top_n:
        ranked = ranked[:top_n]
    return [_god_row(G, nid, deg, "degree") for nid, deg in ranked]


def _god_row(G: Graph, nid: str, value: float, metric: str) -> dict[str, Any]:
    nd = G.get_node(nid, {}) or {}
    return {
        "id": nid,
        "label": nd.get("label", nid),
        "file_type": nd.get("file_type", ""),
        "source_file": nd.get("source_file", ""),
        metric: value,
        "community": None,
    }


def pagerank(G: Graph, damping: float = 0.85, iterations: int = 100, tol: float = 1e-8) -> dict[str, float]:
    """Power-iteration PageRank, dependency-free, any scale."""
    nodes = list(G.nodes())
    n = len(nodes)
    if n == 0:
        return {}
    out_deg: dict[str, int] = {}
    for u in nodes:
        nb = list(G.nbrs(u))
        out_deg[u] = len(nb) or 0
    rank = {u: 1.0 / n for u in nodes}
    for _ in range(iterations):
        converged = True
        dangling = sum(rank[u] for u in nodes if out_deg[u] == 0)
        base = (1.0 - damping) / n + damping * dangling / n
        new = {u: base for u in nodes}
        for u in nodes:
            r = rank[u] * damping
            targets = list(G.nbrs(u))
            if not targets:
                continue
            share = r / len(targets)
            for v in targets:
                if v != u:
                    new[v] += share
        for u in nodes:
            if abs(new[u] - rank[u]) > tol:
                converged = False
                rank[u] = new[u]
            else:
                rank[u] = new[u]
        if converged:
            break
    return rank


def in_degree_out_degree(G: Graph) -> dict[str, dict[str, int]]:
    if not G.is_directed():
        return {u: {"in": 0, "out": 0} for u in G.nodes()}
    res: dict[str, dict[str, int]] = {}
    for u in G.nodes():
        res.setdefault(u, {"in": 0, "out": 0})
        res[u]["out"] = len(list(G.nbrs(u)))
    for u in G.nodes():
        for v in G.nbrs(u):
            res[v]["in"] += 1
    return res


def bridges_and_articulation(G: Graph) -> tuple[list[tuple[str, str]], list[str]]:
    """Iterative Tarjan for bridges + articulation points (ignores direction)."""
    disc: dict[str, int] = {}
    low: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    is_articulation: set[str] = set()
    bridges: list[tuple[str, str]] = []
    counter = 0

    for root in list(G.nodes()):
        if root in disc:
            continue
        disc[root] = low[root] = counter
        counter += 1
        parent[root] = None
        root_children = 0
        stack: list[tuple[str, str | None, Any]] = [(root, iter(G.nbrs(root)), None)]
        while stack:
            node, neighbor_iter, par = stack[-1]
            advanced = False
            for nb in neighbor_iter:
                if nb == par:
                    # parent edge (single); parallel duplicates rare - Tarjan standard skips once
                    parent_test = parent.get(node)
                    if par is not None and parent_test == par:
                        continue
                if nb in disc:
                    if disc[nb] < low[node]:
                        low[node] = disc[nb]
                    continue
                disc[nb] = low[nb] = counter
                counter += 1
                parent[nb] = node
                if node == root:
                    root_children += 1
                stack.append((nb, iter(G.nbrs(nb)), node))
                advanced = True
                break
            if advanced:
                continue
            stack.pop()
            if par is not None:
                if low[node] < low[par]:
                    low[par] = low[node]
                if par != root and low[node] >= disc[par]:
                    is_articulation.add(par)
                if low[node] > disc[par]:
                    bridges.append((par, node) if par < node else (node, par))
        if root_children > 1:
            is_articulation.add(root)
    return bridges, sorted(is_articulation)


def find_cycles(G: Graph, limit: int = 40) -> list[list[str]]:
    """Simple cycles via DFS back-edges on the directed view (or directed copy)."""
    H = G
    if not G.is_directed():
        return _undirected_tri_cycles(G, limit)
    index: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: set[str] = set()
    stack: list[str] = []
    counter = 0
    cycles: list[list[str]] = []

    def strongconnect(v: str) -> None:  # noqa: ANN001
        nonlocal counter, limit
        index[v] = counter
        lowlink[v] = counter
        counter += 1
        stack.append(v)
        on_stack.add(v)
        for w in H.nbrs(v):
            if w not in index:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], index[w])
        if lowlink[v] == index[v]:
            comp: list[str] = []
            while True:
                w = stack.pop()
                on_stack.discard(w)
                comp.append(w)
                if w == v:
                    break
            if len(comp) > 1 and limit > 0:
                cycles.append(sorted(comp))
                limit -= 1

    for v in list(G.nodes()):
        if v not in index:
            strongconnect(v)
    return cycles


def _undirected_tri_cycles(G: Graph, limit: int) -> list[list[str]]:
    out: list[list[str]] = []
    for u, v in G.edges_view():
        common = [n for n in G.nbrs(u) if n in set(G.nbrs(v))]
        for c in common:
            tri = sorted({u, v, c})
            if tri not in out:
                out.append(tri)
            if len(out) >= limit:
                return out
    return out


def graph_diff(G_old: Graph, G_new: Graph) -> dict[str, Any]:
    old_nodes = set(G_old.nodes())
    new_nodes = set(G_new.nodes())
    old_edges = {tuple(sorted((u, v))) for u, v in G_old.edges_view()}
    new_edges = {tuple(sorted((u, v))) for u, v in G_new.edges_view()}
    added_nodes = sorted(new_nodes - old_nodes)
    removed_nodes = sorted(old_nodes - new_nodes)
    added_edges = sorted(new_edges - old_edges)
    removed_edges = sorted(old_edges - new_edges)
    label_of = lambda nid: (G_new.get_node(nid, {}) or {}).get("label") or (G_old.get_node(nid, {}) or {}).get("label") or nid  # noqa: E731
    return {
        "summary": (
            f"+{len(added_nodes)} nodes, -{len(removed_nodes)} nodes, "
            f"+{len(added_edges)} edges, -{len(removed_edges)} edges"
        ),
        "new_nodes": [{"id": n, "label": label_of(n)} for n in added_nodes[:200]],
        "removed_nodes": [{"id": n, "label": label_of(n)} for n in removed_nodes[:200]],
        "new_edges": [{"source": a, "target": b} for a, b in added_edges[:400]],
        "removed_edges": [{"source": a, "target": b} for a, b in removed_edges[:400]],
    }


def surprising_connections(G: Graph, communities: dict[int, list[str]], top_n: int = 12) -> list[dict[str, Any]]:
    """Edges that bridge two communities - structurally surprising connections."""
    node_comm: dict[str, int] = {}
    for cid, members in communities.items():
        for n in members:
            node_comm[n] = cid
    scored: list[dict[str, Any]] = []
    for u, v in G.edges_view():
        cu, cv = node_comm.get(u, -1), node_comm.get(v, -1)
        if cu == cv or cu < 0 or cv < 0:
            continue
        du, dv = G.degree(u), G.degree(v)
        score = min(du, dv) + G.degree(u) * G.degree(v) ** 0.5
        data = G.get_edge_data(u, v, {}) or {}
        scored.append(
            {
                "source": u,
                "target": v,
                "relation": data.get("relation", ""),
                "confidence": data.get("confidence", ""),
                "score": score,
                "communities": (cu, cv),
            }
        )
    scored.sort(key=lambda r: -r["score"])
    if top_n:
        scored = scored[:top_n]
    label_of = lambda nid: (G.get_node(nid, {}) or {}).get("label") or nid  # noqa: E731
    for r in scored:
        r["source_label"] = label_of(r["source"])
        r["target_label"] = label_of(r["target"])
    return scored


def suggest_questions(G: Graph, communities: dict[int, list[str]], labels: dict[int, str], limit: int = 7) -> list[dict[str, Any]]:
    node_comm = {n: c for c, ms in communities.items() for n in ms}
    label_of = lambda nid: (G.get_node(nid, {}) or {}).get("label") or nid  # noqa: E731
    comms = sorted(communities)
    questions: list[dict[str, Any]] = []

    # bridge questions from surprising edges
    surprises = surprising_connections(G, communities, top_n=20)
    candidates = [
        {
            "question": f"How does {label_of(s['source'])} connect to {label_of(s['target'])} across communities {labels.get(s['communities'][0], s['communities'][0])} and {labels.get(s['communities'][1], s['communities'][1])}?",
            "kind": "bridge",
            "seed": s["source"],
            "target": s["target"],
        }
        for s in surprises[:5]
        if s["source"] != s["target"]
    ]
    questions.extend(candidates)

    # isolate/under-connected nodes
    isolated = [n for n in G.nodes() if G.degree(n) == 0]
    if isolated:
        questions.append(
            {"question": f"What is {label_of(sorted(isolated)[0])} - it has no structural connections in this graph?",
             "kind": "isolation", "seed": sorted(isolated)[0]}
        )

    # big communities
    big = sorted(comms, key=lambda c: -len(communities[c]))
    if big:
        c0 = big[0]
        questions.append(
            {"question": f"What are the responsibilities of the {labels.get(c0, c0)} community ({len(communities[c0])} nodes)?",
             "kind": "community-overview", "seed": c0}
        )
    if len(big) > 1:
        c1 = big[1]
        questions.append(
            {"question": f"Where do {labels.get(big[0], big[0])} and {labels.get(c1, c1)} overlap?",
             "kind": "overlap", "seed": big[0], "target": c1}
        )

    # inferred-heavy spots
    inferred_top = []
    for u, v in G.edges_view():
        d = G.get_edge_data(u, v, {}) or {}
        if d.get("confidence") == "INFERRED":
            inferred_top.append((u, v))
    if inferred_top:
        questions.append(
            {"question": f"Why does the graph infer a link between {label_of(inferred_top[0][0])} and {label_of(inferred_top[0][1])}?",
             "kind": "inferred", "seed": inferred_top[0][0]}
        )

    out: list[dict[str, Any]] = []
    seen_str: set[str] = set()
    for q in questions:
        if q["question"] in seen_str:
            continue
        seen_str.add(q["question"])
        out.append(q)
    return out[: limit if limit > 0 else 7]


def category_profile(G: Graph) -> dict[str, int]:
    counts: dict[str, int] = {}
    for nd in G.nodes_data():
        counts[nd[1].get("file_type", "other")] = counts.get(nd[1].get("file_type", "other"), 0) + 1
    return counts


def confidence_profile(G: Graph) -> dict[str, int]:
    counts = {"EXTRACTED": 0, "INFERRED": 0, "AMBIGUOUS": 0, "other": 0}
    for u, v in G.edges_view():
        d = G.get_edge_data(u, v, {}) or {}
        conf = d.get("confidence", "other")
        counts[conf] = counts.get(conf, 0) + 1
    return counts


def locate_isolated(G: Graph, top_n: int = 50) -> list[str]:
    iso = sorted(n for n in G.nodes() if G.degree(n) == 0)
    return iso if not top_n else iso[:top_n]
