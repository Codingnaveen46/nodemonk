"""nodemonk.build - turn extraction products into the working graph."""

from __future__ import annotations

from typing import Any

from .graph import Graph


def build(nodes: list[dict[str, Any]], edges: list[dict[str, Any]], directed: bool = False) -> tuple[Graph, dict[str, Any]]:
    G = Graph(directed=directed)
    for nd in nodes:
        G.add_node(nd["id"], **{k: v for k, v in nd.items() if k != "id"})
    for e in edges:
        weight = float(e.get("weight") or e.get("confidence_score") or 1.0)
        G.add_edge(e["source"], e["target"], keep_existing=True,
                   **{k: v for k, v in e.items() if k not in ("source", "target") and v is not None})
        data = G.get_edge_data(e["source"], e["target"])
        if data is not None and "weight" not in data:
            data["weight"] = weight
    meta = {"nodes": G.number_of_nodes(), "edges": G.number_of_edges()}
    return G, meta


def build_from_extraction(extraction: dict[str, Any]) -> Graph:
    G, _meta = build(extraction.get("nodes", []), extraction.get("edges", []))
    for he in extraction.get("hyperedges", []) or []:
        members = [m for m in he.get("nodes", []) if G.has_node(m)]
        if len(members) < 3:
            continue
        hid = f"hyperedge::{he.get('id') or he.get('label', 'hyperedge')}"
        G.add_node(hid, label=he.get("label") or hid, file_type="hyperedge",
                   source_file=he.get("source_file", ""), hyperedge=True)
        for m in members:
            G.add_edge(hid, m, relation="participate_in",
                       confidence=he.get("confidence", "INFERRED"),
                       confidence_score=float(he.get("confidence_score", 0.75) or 0.75),
                       weight=1.0)
    return G


def infer_file_type(node: dict[str, Any]) -> str:
    ft = node.get("file_type")
    if ft:
        return ft
    if str(node.get("source_file", "")).endswith(".md"):
        return "document"
    return "code"
