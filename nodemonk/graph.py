"""nodemonk.graph - the graph engine.

A dependency-free graph structure tuned for the scale nodemonk targets:
millions of nodes / edges without artificial caps.  The API surface mirrors
the subset of NetworkX everyone actually uses, so algorithms in this package
read the same way, but every hot path is a plain dict walk and undirected
adjacency stores each undirected edge *once* (attribute dict shared between
both directions) instead of per-orientation copies.
"""

from __future__ import annotations

import hashlib
from typing import Any, Callable, Iterable, Iterator


class Graph:
    """Undirected or directed graph with per-node and per-edge attributes."""

    __slots__ = ("directed", "_nodes", "_adj", "_pred", "_ecount")

    def __init__(self, directed: bool = False) -> None:
        self.directed = directed
        # node_id -> attribute dict
        self._nodes: dict[str, dict[str, Any]] = {}
        # undirected: node -> neighbor -> shared edge attr dict
        # directed:   node -> successor -> shared edge attr dict
        self._adj: dict[str, dict[str, dict[str, Any]]] = {}
        # only used on directed graphs: node -> predecessor -> shared attr dict
        self._pred: dict[str, dict[str, dict[str, Any]]] | None = None
        if directed:
            self._pred = {}
        self._ecount = 0

    # ------------------------------------------------------------------ #
    # containers

    def __contains__(self, node: str) -> bool:
        return node in self._nodes

    def __iter__(self) -> Iterator[str]:
        return iter(self._nodes)

    def __len__(self) -> int:
        return len(self._nodes)

    def number_of_nodes(self) -> int:
        return len(self._nodes)

    def number_of_edges(self) -> int:
        return self._ecount

    def is_directed(self) -> bool:
        return self.directed

    # ------------------------------------------------------------------ #
    # node ops

    def add_node(self, node: str, **attrs: Any) -> None:
        data = self._nodes.get(node)
        if data is None:
            self._nodes[node] = dict(attrs)
            self._adj[node] = {}
            if self._pred is not None:
                self._pred[node] = {}
        else:
            data.update(attrs)

    def get_node(self, node: str, default: Any = None) -> Any:
        return self._nodes.get(node, default)

    def node_attrs(self, node: str) -> dict[str, Any] | None:
        return self._nodes.get(node)

    def has_node(self, node: str) -> bool:
        return node in self._nodes

    def nodes(self, data: bool = False) -> Iterable:
        if not data:
            return iter(self._nodes)
        return ((n, d) for n, d in self._nodes.items())

    def nodes_data(self) -> Iterable[tuple[str, dict[str, Any]]]:
        return self._nodes.items()

    def node_data_map(self) -> dict[str, dict[str, Any]]:
        return self._nodes

    def remove_node(self, node: str) -> None:
        if node not in self._nodes:
            return
        for nb in list(self._adj[node]):
            self._remove_edge_entry(node, nb)
        del self._nodes[node]
        del self._adj[node]
        if self._pred is not None:
            for pred in list(self._pred[node]):
                self._adj[pred].pop(node, None)
            del self._pred[node]

    # ------------------------------------------------------------------ #
    # edge ops

    def add_edge(
        self, u: str, v: str, weight: float = 1.0, keep_existing: bool = False, **attrs: Any
    ) -> dict[str, Any]:
        """Add an edge. Missing endpoint nodes are auto-created (like nx).
        Returns the edge attribute dict.
        """
        if u not in self._nodes:
            self.add_node(u)
        if v not in self._nodes:
            self.add_node(v)
        existing = self._adj[u].get(v)
        if existing is not None and keep_existing:
            return existing
        if existing is not None:
            existing.update(attrs)
            existing.setdefault("weight", weight)
            return existing
        data = dict(attrs)
        data.setdefault("weight", weight)
        self._adj[u][v] = data
        if u == v:
            self._ecount += 1  # self-loops count once
            if self._pred is not None:
                self._pred[u][v] = data
            return data
        if self._pred is not None:
            self._pred[v][u] = data
        else:
            # undirected: make the neighbor see the same shared dict
            self._adj[v][u] = data
        self._ecount += 1
        return data

    def has_edge(self, u: str, v: str) -> bool:
        return u in self._nodes and v in self._adj[u]

    def get_edge_data(self, u: str, v: str, default: Any = None) -> Any:
        if u not in self._adj:
            return default
        return self._adj[u].get(v, default)

    def remove_edge(self, u: str, v: str) -> None:
        self._remove_edge_entry(u, v)
        if not self.is_directed():
            self._remove_edge_entry(v, u)

    def _remove_edge_entry(self, u: str, v: str) -> None:
        if u in self._adj and v in self._adj[u]:
            del self._adj[u][v]
            self._ecount -= 1

    def edges(self, data: bool = False) -> Iterable:
        """Undirected graphs: each edge appears exactly once (canonical view)."""
        return (
            ((u, v, d) for u, nb in self._adj.items() for v, d in nb.items() if self.is_directed() or u <= v)
            if data
            else ((u, v) for u, nb in self._adj.items() for v in nb if self.is_directed() or u <= v)
        )

    def edges_view(self) -> Iterator[tuple[str, str]]:
        return iter(self.edges(False))

    def neighbors(self, node: str) -> Iterator[str]:
        if node not in self._adj:
            return iter(())
        return iter(self._adj[node])

    def nbrs(self, node: str) -> dict[str, dict[str, Any]]:
        return self._adj[node]

    def predecessors(self, node: str) -> Iterator[str]:
        if not self.is_directed():
            return self.neighbors(node)
        pred = self._pred.get(node) if self._pred is not None else None
        return iter(pred or {})

    def successors(self, node: str) -> Iterator[str]:
        return self.neighbors(node)

    def degree(self, node: str) -> int:
        if node not in self._adj:
            return 0
        if self.is_directed():
            return len(self._adj[node]) + len(self._pred.get(node) or {})
        loop = 1 if node in self._adj[node] else 0
        return len(self._adj[node]) + loop

    def degree_map(self) -> dict[str, int]:
        if self.is_directed():
            return {
                n: len(self._adj[n]) + len(self._pred.get(n) or {}) for n in self._nodes
            }
        return {n: len(self._adj[n]) + (1 if n in self._adj[n] else 0) for n in self._nodes}

    # ------------------------------------------------------------------ #
    # views / transforms

    def subgraph(self, nodes: Iterable[str]) -> "Graph":
        keep = set(nodes)
        H = Graph(directed=self.directed)
        for n, d in self._nodes.items():
            if n in keep:
                H._nodes[n] = d
                H._adj[n] = {}
                if H._pred is not None:
                    H._pred[n] = {}
        for u in H._adj:
            for v in (self._pred[u] if self.is_directed() else self._adj[u]):
                if v in keep and self.is_directed():
                    H._adj[u][v] = self._adj[u][v]
                    H._pred[v][u] = self._adj[u][v]
                    H._ecount += 1
        if not self.is_directed():
            seen: set[str] = set()
            for u in H._adj:
                for v in self._adj[u]:
                    if v not in keep or v == u:
                        continue
                    key = u + "\x00" + v if u < v else v + "\x00" + u
                    if key in seen:
                        continue
                    seen.add(key)
                    H._adj[u][v] = self._adj[u][v]
                    H._adj[v][u] = self._adj[u][v]
                    H._ecount += 1
        return H

    def to_undirected(self) -> "Graph":
        # adjacency already mirrors for undirected builds; for directed builds
        # merge successor+predecessor views into the neighbour union.
        if not self.is_directed():
            return self
        H = Graph(directed=False)
        for n, d in self._nodes.items():
            H.add_node(n, **d)
        for u in self._adj:
            for v, data in self._adj[u].items():
                existing = H.get_edge_data(u, v)
                if existing is not None:
                    if existing is not data:
                        existing.update({k: v2 for k, v2 in data.items() if v2 is not None})
                    continue
                H.add_edge(u, v, **data)
        return H

    def clear(self) -> None:
        self._nodes.clear()
        self._adj.clear()
        self._ecount = 0
        if self._pred is not None:
            self._pred.clear()

    # ------------------------------------------------------------------ #
    # node-link (JSON) serialisation with explicit arc direction stamping

    def to_node_link(self) -> dict[str, Any]:
        links: list[dict[str, Any]] = []
        if self.is_directed():
            for u, v, d in self.edges(True):
                link = {"source": u, "target": v, **d}
                links.append(link)
        else:
            # undirected: arc order is the direction (same convention as the
            # format we interoperate with: source -> target when present)
            for u, v in self.edges(False):
                d = self._adj[u][v]
                link = {"source": u, "target": v, **d}
                links.append(link)
        return {
            "directed": self.directed,
            "multigraph": False,
            "nodes": [{"id": n, **d} for n, d in self._nodes.items()],
            "links": links,
        }

    @classmethod
    def from_node_link(cls, data: dict[str, Any]) -> "Graph":
        G = cls(directed=bool(data.get("directed")))
        for nd in data.get("nodes", []):
            attrs = {k: v for k, v in nd.items() if k != "id"}
            G.add_node(nd["id"], **attrs)
        for ld in data.get("links", []):
            src = ld.get("_src", ld.get("source"))
            tgt = ld.get("_tgt", ld.get("target"))
            if src is None or tgt is None:
                continue
            attrs = {
                k: v
                for k, v in ld.items()
                if k not in ("source", "target", "_src", "_tgt")
            }
            G.add_edge(src, tgt, **attrs)
        return G

    # ------------------------------------------------------------------ #
    # convenience counting

    def ecount_exact(self) -> int:
        if not self.is_directed():
            seen = 0
            for u, nb in self._adj.items():
                loop = 1 if u in nb else 0
                bidir = sum(1 for v in nb if u < v)
                seen += loop + bidir
            return seen
        return sum(len(nb) for nb in self._adj.values())


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8", "replace")).hexdigest()[:16]


def stable_id(*parts: str) -> str:
    """Deterministic idly composed id with sane separators."""
    return "_".join(p.strip().replace("/", "_").replace("\\", "_") for p in parts if p)
