"""nodemonk.benchmark - token compression measurement (corpus vs graph).

The number that justifies the project: reading your whole corpus vs reading
the graph. No LLM call required - we approximate "tokens to answer a lookup
question" by file volumes the answering context would need.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


def run_benchmark(graph_path: str | Path, corpus_words: int | None = None) -> dict[str, Any]:
    path = Path(graph_path)
    data = json.loads(path.read_text(encoding="utf-8"))
    node_count = len(data.get("nodes", []))
    edge_count = len(data.get("links", []))
    node_chars = sum(len(str(n.get("label", ""))) + 3 for n in data.get("nodes", []))
    edge_chars = sum(len(str(l.get("relation", ""))) + 12 for l in data.get("links", []))
    graph_tokens = (node_chars + edge_chars) // 4
    corpus_words = corpus_words if corpus_words is not None else _words_from_meta(data)
    corpus_tokens = int(corpus_words * 1.35)
    ratio = graph_tokens / corpus_tokens if corpus_tokens else 0.0
    return {
        "corpus_tokens": corpus_tokens,
        "graph_tokens": graph_tokens,
        "compression_ratio": round(ratio, 4),
        "savings_pct": round((1 - ratio) * 100, 1) if corpus_tokens else 0.0,
        "nodes": node_count,
        "edges": edge_count,
    }


def _words_from_meta(data: dict[str, Any]) -> int:
    meta = data.get("detection") or {}
    return int(meta.get("total_words", 0))


def print_benchmark(result: dict[str, Any]) -> str:
    return (
        f"benchmark: corpus ≈ {result['corpus_tokens']:,} tokens -> "
        f"graph ≈ {result['graph_tokens']:,} tokens "
        f"({result['compression_ratio']:.2%} of original, {result['savings_pct']:.1f}% compression)"
    )
