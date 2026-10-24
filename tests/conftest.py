"""Shared fixtures & helpers for the test suite."""

from __future__ import annotations

import json
from pathlib import Path

from nodemonk.export import to_json
from nodemonk.graph import Graph


def build_toy_graph_file(tmp_path: Path) -> Path:
    g = Graph()
    g.add_node("a", label="AlphaMain", file_type="code", source_file="x.py")
    g.add_node("b", label="BetaHelper", file_type="code", source_file="y.py")
    g.add_node("c", label="GammaDocs", file_type="document", source_file="notes.md")
    g.add_edge("a", "b", relation="calls", confidence="EXTRACTED", confidence_score=1.0)
    g.add_edge("a", "c", relation="references", confidence="INFERRED", confidence_score=0.85)
    comms = {0: ["a", "b", "c"]}
    labels = {0: "Everything"}
    out = tmp_path / "graph.json"
    to_json(g, comms, labels, out)
    return out
