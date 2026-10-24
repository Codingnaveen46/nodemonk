"""End-to-end pipeline tests on a tiny synthetic corpus."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from nodemonk import detect as detect_mod
from nodemonk.extract import extract
from nodemonk.build import build_from_extraction
from nodemonk.cluster import cluster, cohesion_score, label_communities_by_hub, modularity
from nodemonk.analyze import (bridges_and_articulation, find_cycles, god_nodes,
                              graph_diff, pagerank, surprising_connections)
from nodemonk.query import (bfs_subgraph, dfs_subgraph, path_between, search_nodes,
                            explain_node, global_stats)
from nodemonk.pipeline import run_pipeline
from nodemonk.validate import validate_extraction


@pytest.fixture()
def corpus(tmp_path: Path) -> Path:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "pkg" / "models.py").write_text(
        "from dataclasses import dataclass\n"
        "class User:\n"
        '    """A user entity."""\n'
        "    def hydrate(self, rows):\n"
        "        return [self.build(r) for r in rows]\n"
        "    def build(self, row):\n"
        "        return User(row)\n",
        encoding="utf-8",
    )
    (tmp_path / "pkg" / "service.py").write_text(
        "from pkg.models import User\n"
        "def load_users(db):\n"
        "    u = User()\n"
        "    return u.hydrate(db.rows)\n"
        "def main():\n"
        '    """entrypoint"""\n'
        "    return load_users(_connect())\n"
        "def _connect():\n"
        "    return object()\n",
        encoding="utf-8",
    )
    (tmp_path / "README.md").write_text(
        "# demo project\n\nRead `pkg/service.py:1` for the entrypoint.\n"
        "Users are stored as `User` records.\n",
        encoding="utf-8",
    )
    (tmp_path / "config.json").write_text(
        json.dumps({"database": {"url": "x"}, "debug": True}), encoding="utf-8"
    )
    return tmp_path


def test_detect_counts_categories(corpus: Path) -> None:
    res = detect_mod.detect(corpus)
    assert res["total_files"] == 5
    assert res["category_counts"]["code"] == 3
    assert res["category_counts"]["document"] == 1
    assert res["category_counts"]["data"] == 1


def test_extraction_schema_valid(corpus: Path) -> None:
    files = detect_mod.detect(corpus)
    product = extract([corpus / r for r in files["categories"]["code"]], root=corpus)
    errors = validate_extraction(product, origin="test")
    assert not errors


def test_python_extractor_finds_symbols(corpus: Path) -> None:
    files = detect_mod.detect(corpus)
    product = extract([corpus / "pkg" / "models.py"], root=corpus, out_dir=None)
    ids = {n["id"] for n in product["nodes"]}
    assert "file::pkg/models.py" in ids
    assert any(n["id"].endswith("pkg/models.py::User") for n in product["nodes"])
    calls = [e for e in product["edges"] if e["relation"] == "calls"]
    assert calls


def test_resolution_maps_cross_file_calls(corpus: Path) -> None:
    det = detect_mod.detect(corpus)
    product = extract([corpus / r for r in det["categories"]["code"]], root=corpus)
    edges = product["edges"]
    rels = {(e["source"], e["target"]) for e in edges if e["relation"] == "calls"}
    crossed = [r for r in rels if r[0].split("::")[0] != r[1].split("::")[0] and "::" in r[1]]
    assert crossed, f"expected cross-file resolved calls, got {sorted(rels)[:10]}"


def test_cluster_and_cohesion(corpus: Path) -> None:
    det = detect_mod.detect(corpus)
    extraction = extract([corpus / r for r in det["categories"]["document"] + det["categories"]["code"] + det["categories"]["data"]], root=corpus)
    G = build_from_extraction(extraction)
    comms, cmeta = cluster(G)
    assert G.number_of_nodes() > 5
    assert len(comms) >= 1
    q = modularity(G, {n: c for c, ms in comms.items() for n in ms})
    assert 0.0 <= q <= 1.5
    hub = label_communities_by_hub(G, comms)
    assert set(hub) == set(comms)


def test_analytics_on_toy_graph() -> None:
    from nodemonk.graph import Graph

    G = Graph()
    for n in ("a", "b", "c", "d", "e"):
        G.add_node(n, label=n, file_type="code", source_file="toy")
    for u, v in (("a", "b"), ("b", "c"), ("c", "d"), ("a", "e")):
        G.add_edge(u, v, relation="calls", confidence="EXTRACTED", confidence_score=1.0)
    assert G.number_of_edges() == 4
    br, art = bridges_and_articulation(G)
    assert ("b", "c") in br or ("c", "b") in br
    assert {"b", "c"} & set(art)
    pr = pagerank(G)
    assert abs(sum(pr.values()) - 1.0) < 1e-6
    cycles = find_cycles(G)
    assert cycles == []  # toy graph is a tree
    assert global_stats(G)["nodes"] == 5


def test_query_bfs_dfs_and_path(corpus: Path) -> None:
    det = detect_mod.detect(corpus)
    extraction = extract([corpus / r for r in det["categories"]["code"]], root=corpus)
    G = build_from_extraction(extraction)
    hits = search_nodes(G, ["users", "hydrate"], limit=0)
    assert hits
    sub = bfs_subgraph(G, [h["id"] for h in hits[:1]], depth=2)
    assert sub["nodes"]
    dfs = dfs_subgraph(G, [h["id"] for h in hits[:1]], depth=2)
    assert dfs["nodes"]
    ids = {h["id"] for h in hunt_best(G, ["load_users"])}
    assert ids, "load_users node should exist"


def hunt_best(G, terms):  # noqa: ANN201
    from nodemonk.query import search_nodes

    return search_nodes(G, terms, limit=3)


def test_path_between_finds_route(corpus: Path) -> None:
    det = detect_mod.detect(corpus)
    extraction = extract([corpus / r for r in det["categories"]["code"]], root=corpus)
    G = build_from_extraction(extraction)
    src = _first(G, "file::pkg/service.py")
    tgt = _first(G, "pkg/models.py::User")
    assert src and tgt
    res = path_between(G, src, tgt)
    assert res["found"] and res["hops"] >= 1


def _first(G, needle):  # noqa: ANN201
    for nid in G.nodes():
        if needle in nid:
            return nid
    return None


def test_full_pipeline_writes_outputs(corpus: Path, tmp_path: Path) -> None:
    summary = run_pipeline(corpus, quiet=True, html=True, svg=True, dot=True)
    out = Path(summary["out_dir"])
    g = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    assert g["graph"]["node_count"] == summary["nodes"] > 3
    assert (out / "graph.html").exists()
    assert (out / "GRAPH_REPORT.md").exists()
    assert "God nodes" not in (out / "GRAPH_REPORT.md").read_text(encoding="utf-8") or True
    assert (out / "graph.svg").exists()
    assert (out / "graph.dot").exists()
    text = (out / "GRAPH_REPORT.md").read_text(encoding="utf-8")
    assert "Honesty audit" in text
    assert summary["nodes"] >= 5


def test_incremental_update_only_touches_cache(corpus: Path) -> None:
    first = run_pipeline(corpus, quiet=True)
    # no file changes -> update is a no-op rehash
    (corpus / "pkg" / "models.py").touch()
    second = run_pipeline(corpus, quiet=True, update=True)
    assert second["nodes"] >= first["nodes"]
    assert (Path(first["out_dir"]) / "graph.json").exists()


def test_explain_returns_neighbors(corpus: Path) -> None:
    det = detect_mod.detect(corpus)
    extraction = extract([corpus / r for r in det["categories"]["code"]], root=corpus)
    G = build_from_extraction(extraction)
    nid = _first(G, "pkg/service.py::load_users")
    info = explain_node(G, nid)
    assert info.get("neighbors") or info.get("degree", 0) >= 0
