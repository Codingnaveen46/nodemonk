"""nodemonk.cluster - dependency-free community detection.

Implements two-layer Louvain modularity optimisation from scratch (weighted,
deterministic, resolution-scaled) plus label propagation for gigantic graphs.
AMBIGUOUS-confidence edges are weight-scaled by `ambiguous_scale` (default 0.5)
so low-trust linkage does not glue otherwise independent clusters together.
Outputs {community_id: [members]} with stable, size-descending ids.
"""

from __future__ import annotations

import random
from typing import Any, Iterable

from .graph import Graph

_MAX_COMMUNITY_FRACTION = 0.25
_MIN_SPLIT_SIZE = 12
_COHESION_SPLIT_THRESHOLD = 0.02
_COHESION_SPLIT_MIN_SIZE = 60


def _weighted_adjacency(G: Graph, ambiguous_scale: float) -> tuple[list[int], list[dict[int, float]], float]:
    order = sorted(G.nodes())
    idx = {n: i for i, n in enumerate(order)}
    deg = [0] * len(order)
    adj: list[dict[int, float]] = [dict() for _ in order]
    m2 = 0.0
    for u, v in G.edges_view():
        data = G.get_edge_data(u, v, {})
        w = float(data.get("weight", 1.0) or 1.0)
        if data.get("confidence") == "AMBIGUOUS":
            w = max(0.0, w * ambiguous_scale)
        if w <= 0.0:
            continue
        iu, iv = idx[u], idx[v]
        adj[iu][iv] = adj[iu].get(iv, 0.0) + w
        deg[iu] += w
        if iu != iv:
            adj[iv][iu] = adj[iv].get(iu, 0.0) + w
            deg[iv] += w
        m2 += w if iu == iv else 2 * w
    return deg, adj, m2


def _one_level(deg: list[float], adj: list[dict[int, float]], m2: float, resolution: float,
               rng: random.Random, pass_limit: int = 64) -> list[int]:
    n = len(adj)
    comm = list(range(n))
    tot = [deg[i] for i in range(n)]
    order = list(range(n))
    stepped = 0
    improved = True
    while improved and stepped < pass_limit:
        stepped += 1
        improved = False
        rng.shuffle(order)
        for u in order:
            cu = comm[u]
            own_weight = 0.0
            totals: dict[int, float] = {}
            for v, w in adj[u].items():
                cv = comm[v]
                totals[cv] = totals.get(cv, 0.0) + w
                if cv == cu:
                    own_weight += w
            own_weight += adj[u].get(cu, 0.0) if cu in adj[u] else 0.0
            gain_self = own_weight - resolution * tot[cu] * deg[u] / m2
            #  remove u from its community
            tot[cu] -= deg[u]
            best_comm = cu
            best_gain = gain_self
            for cv, wc in totals.items():
                if cv == cu:
                    continue
                gain = wc - resolution * tot[cv] * deg[u] / m2
                if gain > best_gain + 1e-12 or (gain > best_gain - 1e-12 and cv < best_comm):
                    best_gain = gain
                    best_comm = cv
            comm[u] = best_comm
            tot[best_comm] += deg[u]
            if best_comm != cu:
                improved = True
    return comm


def _aggregate(adj: list[dict[int, float]], comm: list[int]) -> tuple[list[int], list[dict[int, float]], float, int]:
    remap: dict[int, int] = {}
    for c in comm:
        remap.setdefault(c, len(remap))
    n2 = len(remap)
    deg2: list[float] = [0.0] * n2
    adj2: list[dict[int, float]] = [{} for _ in range(n2)]
    m2 = 0.0
    for u, nbrs in enumerate(adj):
        cu = remap[comm[u]]
        for v, w in nbrs.items():
            cv = remap[comm[v]]
            adj2[cu][cv] = adj2[cu].get(cv, 0.0) + w
            deg2[cu] += w
            if u != v:
                m2 += 2 * w
            else:
                m2 += w
    return deg2, adj2, m2, n2


def louvain_nodes_to_comm(
    order: list[str],
    deg: list[float],
    adj: list[dict[int, float]],
    m2: float,
    resolution: float,
    seed: int = 42,
) -> dict[str, int]:
    """Full multi-level Louvain over index-space. Returns member -> community id."""
    rng = random.Random(seed)
    n_levels = max(len(order), 1)

    # level-0 structures: super-node i contains real node i
    members: list[list[int]] = [[i] for i in range(n_levels)]
    cur_adj = adj
    cur_deg = deg
    cur_m2 = m2

    for _level in range(24):
        comm = _one_level(cur_deg, cur_adj, cur_m2, resolution, rng)
        n_groups = len(set(comm))
        if n_groups == len(cur_adj):
            break  # already maximal granularity gain in modularity break-even
        # aggregate: regroup members per comm
        gather: dict[int, list[int]] = {}
        for idx, c in enumerate(comm):
            gather.setdefault(c, []).extend(members[idx])
        members = [gather[c] for c in sorted(gather)]
        # build the aggregated adjacency in comm space
        remap = {c: i for i, c in enumerate(sorted(gather))}
        n2 = len(remap)
        adj2: list[dict[int, float]] = [{} for _ in range(n2)]
        deg2: list[float] = [0.0] * n2
        m22 = 0.0
        for u, nbrs in enumerate(cur_adj):
            cu = remap[comm[u]]
            for v, w in nbrs.items():
                cv = remap[comm[v]]
                adj2[cu][cv] = adj2[cu].get(cv, 0.0) + w
                deg2[cu] += w
                if u != v:
                    m22 += 2 * w
                else:
                    m22 += w
        cur_adj, cur_deg, cur_m2 = adj2, deg2, m22

    result: dict[str, int] = {}
    for comm_id, member_indices in enumerate(members):
        for real_idx in member_indices:
            result[order[real_idx]] = comm_id
    return result


def _louvain_partition(G: Graph, resolution: float, ambiguous_scale: float, seed: int) -> dict[str, int]:
    deg, adj, m2 = _weighted_adjacency(G, ambiguous_scale)
    order = sorted(G.nodes())
    if m2 <= 0:
        return {n: 0 for n in order}
    node_comm = louvain_nodes_to_comm(order, deg, adj, m2, resolution, seed)
    return node_comm


def label_propagation(G: Graph, max_iter: int = 60, seed: int = 42) -> dict[str, int]:
    rng = random.Random(seed)
    nodes = sorted(G.nodes())
    if not nodes:
        return {}
    comm = {n: i for i, n in enumerate(nodes)}
    for _ in range(max_iter):
        changed = False
        for n in nodes:
            votes: dict[int, int] = {}
            for nb in G.nbrs(n):
                votes[comm[nb]] = votes.get(comm[nb], 0) + 1
            if not votes:
                continue
            best = max(votes.items(), key=lambda kv: (kv[1], -kv[0]))[0]
            if best != comm[n]:
                comm[n] = best
                changed = True
        if not changed:
            break
    groups: dict[int, list[str]] = {}
    for n, c in comm.items():
        groups.setdefault(c, []).append(n)
    return {c: sorted(m) for c, m in groups.items()}


def cohesion_score(G: Graph, members: Iterable[str]) -> float:
    members = list(members)
    n = len(members)
    if n <= 1:
        return 1.0
    member_set = set(members)
    internal = 0
    for u in members:
        for v, data in G.nbrs(u).items():
            if v in member_set and (u < v or (u == v and data.get("relation") == "calls")):
                internal += 1
    possible = n * (n - 1) / 2
    return internal / possible if possible > 0 else 0.0


def score_all(G: Graph, communities: dict[int, list[str]]) -> dict[int, float]:
    return {cid: cohesion_score(G, members) for cid, members in communities.items()}


def modularity(G: Graph, node_comm: dict[str, int], resolution: float = 1.0) -> float:
    degs = G.degree_map()
    total = sum(degs.values())
    if total <= 0:
        return 0.0
    q = 0.0
    comm_deg: dict[int, float] = {}
    comm_edges: dict[int, float] = {}
    seen: set[str] = set()
    for u, v in G.edges_view():
        w = float(G.get_edge_data(u, v, {}).get("weight", 1.0) or 1.0)
        cu, cv = node_comm.get(u, -1), node_comm.get(v, -1)
        comm_edges[cu] = comm_edges.get(cu, 0.0) + w
        comm_edges[cv] = comm_edges.get(cv, 0.0) + w
    for n, d in degs.items():
        c = node_comm.get(n, -1)
        comm_deg[c] = comm_deg.get(c, 0.0) + d
    for c in set(comm_deg):
        wsum = comm_edges.get(c, 0.0) / 2.0
        q += wsum / total - resolution * (comm_deg[c] / total) ** 2
    return q


def cluster(
    G: Graph,
    resolution: float = 1.0,
    ambiguous_scale: float = 0.5,
    seed: int = 42,
    method: str = "auto",
) -> tuple[dict[int, list[str]], dict[str, Any]]:
    """Detect communities. Returns ({cid: [members]}, diagnostics).

    method: 'auto' (louvain below 150k nodes, label-prop above & mixed back),
            'louvain', 'label-prop', 'none' (single-shell communities).
    """
    meta: dict[str, Any] = {}
    if G.number_of_nodes() == 0:
        return {}, meta
    if G.is_directed():
        G = G.to_undirected()
    if G.number_of_edges() == 0:
        members = {cid: [n] for cid, n in enumerate(sorted(G.nodes()))}
        return members, {"method": "empty"}

    effective = method
    if effective == "auto":
        effective = "louvain" if G.number_of_nodes() < 150_000 else "label-prop"

    if effective == "louvain":
        node_comm = _louvain_partition(G, resolution, ambiguous_scale, seed)
        raw: dict[int, list[str]] = {}
        for n, c in node_comm.items():
            raw.setdefault(c, []).append(n)
        meta["method"] = "louvain"
    elif effective == "label-prop":
        groups = label_propagation(G, seed=seed)
        raw = {c: members for c, members in groups.items()}
        meta["method"] = "label-prop"
    else:
        raw = {0: sorted(G.nodes())}
        meta["method"] = "none"

    # split oversized communities
    max_size = max(_MIN_SPLIT_SIZE, int(G.number_of_nodes() * _MAX_COMMUNITY_FRACTION))
    finalcomms: list[list[str]] = []
    for members in raw.values():
        if len(members) > max_size:
            finalcomms.extend(_split(G, members, ambiguous_scale, seed))
        else:
            finalcomms.append(members)

    # second pass: re-split low-cohesion giant bags
    again: list[list[str]] = []
    for members in finalcomms:
        if len(members) >= _COHESION_SPLIT_MIN_SIZE and cohesion_score(G, members) < _COHESION_SPLIT_THRESHOLD:
            splits = _split(G, members, ambiguous_scale, seed)
            again.extend(splits if len(splits) > 1 else [members])
        else:
            again.append(members)

    again.sort(key=lambda ms: (-len(ms), tuple(sorted(ms))))
    meta["communities"] = len(again)
    meta["modularity"] = None
    return {i: sorted(ms) for i, ms in enumerate(again)}, meta


def _split(G: Graph, members: list[str], ambiguous_scale: float, seed: int) -> list[list[str]]:
    sub = G.subgraph(members)
    if sub.number_of_edges() == 0:
        return [[m] for m in sorted(members)]
    node_comm = _louvain_partition(sub, 1.0, ambiguous_scale, seed)
    groups: dict[int, list[str]] = {}
    for n, c in node_comm.items():
        groups.setdefault(c, []).append(n)
    parts = [sorted(g) for g in groups.values()]
    if len(parts) <= 1:
        return [sorted(members)]
    return parts


def label_communities_by_hub(G: Graph, communities: dict[int, list[str]]) -> dict[int, str]:
    labels: dict[int, str] = {}
    for cid, members in communities.items():
        present = [n for n in members if n in G]
        if not present:
            labels[cid] = f"Community {cid}"
            continue
        hub = min(present, key=lambda n: (-G.degree(n), str(n)))
        label = str(G.get_node(hub, {}).get("label") or hub)
        label = label[:-2] if label.endswith("()") else label
        labels[cid] = label[:64] or f"Community {cid}"
    return labels


def community_member_sigs(communities: dict[int, list[str]]) -> dict[int, str]:
    import hashlib

    sigs: dict[int, str] = {}
    for cid, members in communities.items():
        h = hashlib.sha256()
        for nid in sorted(members):
            h.update(nid.encode("utf-8", "replace"))
            h.update(b"\x00")
        sigs[cid] = h.hexdigest()[:16]
    return sigs


def remap_communities_to_previous(
    communities: dict[int, list[str]],
    previous: dict[str, int],
) -> dict[int, list[str]]:
    new_sets = {cid: set(m) for cid, m in communities.items()}
    old_sets: dict[int, set[str]] = {}
    for n, c in previous.items():
        old_sets.setdefault(c, set()).add(n)
    overlaps: list[tuple[int, int, int]] = []
    for oc, old_nodes in old_sets.items():
        for nc, new_nodes in new_sets.items():
            inter = len(old_nodes & new_nodes)
            if inter:
                overlaps.append((inter, oc, nc))
    overlaps.sort(key=lambda t: (-t[0], t[1], t[2]))
    new_to_final: dict[int, int] = {}
    used: set[int] = set()
    matched_new: set[int] = set()
    for inter, oc, nc in overlaps:
        if oc in used or nc in matched_new:
            continue
        new_to_final[nc] = oc
        used.add(oc)
        matched_new.add(nc)
    unmatched = [c for c in communities if c not in matched_new]
    unmatched.sort(key=lambda c: (-len(communities[c]), tuple(sorted(communities[c]))))
    nxt = 0
    for c in unmatched:
        while nxt in used:
            nxt += 1
        new_to_final[c] = nxt
        used.add(nxt)
        nxt += 1
    return {new_to_final[c]: sorted(m) for c, m in communities.items()}


def label_still_applies(cid: int, members: list[str], previous: dict[str, int], saved_sig: str | None, current_sig: str | None) -> bool:
    if saved_sig and current_sig and saved_sig == current_sig:
        return True
    saved = {n for n, c in previous.items() if c == cid}
    cur = set(members)
    if not saved or not cur:
        return False
    inter = len(saved & cur)
    return inter * 2 > len(saved) and inter * 2 > len(cur)
