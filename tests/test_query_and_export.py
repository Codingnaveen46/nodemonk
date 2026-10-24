"""Query engine, graph engine, exchange formats, MCP, honesty tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from nodemonk.graph import Graph
from nodemonk.build import build
from nodemonk.query import (bfs_subgraph, dfs_subgraph, path_between,
                            search_nodes, shortest_path_all, explain_node,
                            global_stats, neighbor_filter)
from nodemonk.export import to_json, to_graphml, to_cypher, to_dot, to_svg, to_obsidian, load_graph_file
from nodemonk.cluster import cluster, cohesion_score
from nodemonk.viz import write_viz_html


@pytest.fixture()
def G() -> Graph:
    g = Graph()
    g.add_node("a", label="Alpha", file_type="code", source_file="src/a.py", docstring="alpha does things")
    g.add_node("b", label="Beta", file_type="code", source_file="src/b.py")
    g.add_node("c", label="Gamma", file_type="document", source_file="notes/g.md")
    g.add_node("d", label="Delta", file_type="code", source_file="src/d.py")
    g.add_edge("a", "b", relation="calls", confidence="EXTRACTED", confidence_score=1.0)
    g.add_edge("a", "c", relation="references", confidence="INFERRED", confidence_score=0.85)
    g.add_edge("b", "d", relation="calls", confidence="AMBIGUOUS", confidence_score=0.3)
    return g


def test_graph_roundtrip(G: Graph) -> None:
    dump = G.to_node_link()
    H = Graph.from_node_link(dump)
    assert H.number_of_nodes() == 4
    assert H.number_of_edges() == 3
    assert H.get_edge_data("a", "b", {}).get("relation") == "calls"


def test_undirected_edge_counting(G: Graph) -> None:
    assert G.number_of_edges() == 3
    assert len(list(G.edges_view())) == 3
    assert G.degree("a") == 2


def test_search_scores(G: Graph) -> None:
    hits = search_nodes(G, ["alpha"], limit=0)
    assert hits and hits[0]["id"] == "a"
    hits2 = search_nodes(G, ["gamma"], kind="document", limit=0)
    assert hits2 and hits2[0]["id"] == "c"


def test_path_bfs_weighted(G: Graph) -> None:
    res = path_between(G, "a", "d")
    assert res["found"] and res["hops"] == 2
    w = path_between(G, "a", "d", weighted=True)
    assert w["found"] and w["hops"] == 2


def test_bfs_dfs_limitless(G: Graph) -> None:
    sub = bfs_subgraph(G, ["a"], depth=3, limit=0)
    assert set(sub["nodes"]) == {"a", "b", "c", "d"}
    assert len(sub["edges"]) == 3
    d = dfs_subgraph(G, ["a"], depth=3)
    assert set(d["nodes"]) >= {"a", "b", "d"}
    full = shortest_path_all(G, "a")
    assert full["d"]["dist"] == 2


def test_neighbors_filter(G: Graph) -> None:
    nb = neighbor_filter(G, "a", confidence="EXTRACTED")
    assert nb and all(n["confidence"] == "EXTRACTED" for n in nb)


def test_explain(G: Graph) -> None:
    info = explain_node(G, "a")
    assert info["id"] == "a"
    assert info["degree"] == 2
    assert any(n["to"] == "b" for n in info["neighbors"])


def test_stats(G: Graph) -> None:
    st = global_stats(G)
    assert st["nodes"] == 4 and st["edges"] == 3
    assert st["self_loops"] == 0


def test_exports(G: Graph, tmp_path: Path) -> None:
    comms = {0: ["a", "b"], 1: ["c", "d"]}
    labels = {0: "Code side", 1: "Docs side"}
    p = tmp_path / "g.json"
    payload = to_json(G, comms, labels, p, meta={"built_at": "t"})
    loaded, data = load_graph_file(p)
    assert loaded.number_of_nodes() == 4
    assert data["communities"] == {"0": ["a", "b"], "1": ["c", "d"]}
    assert payload["graph"]["schema_version"] >= 2
    gml = to_graphml(G, tmp_path / "g.graphml")
    text = gml.read_text(encoding="utf-8")
    assert "<node id=" in text
    cyp = to_cypher(G, tmp_path / "cypher.txt")
    ct = cyp.read_text(encoding="utf-8")
    assert "MERGE (n:NmNode {" in ct
    dot = to_dot(G, tmp_path / "g.dot")
    assert "--" in dot.read_text(encoding="utf-8")
    svg = to_svg(G, comms, labels, tmp_path / "g.svg")
    assert "<circle" in svg.read_text(encoding="utf-8")
    obs = to_obsidian(G, comms, labels, tmp_path / "vault", cohesion=cohesion_score(G, comms[0]))
    assert obs >= 3
    html = write_viz_html(G, comms, labels, tmp_path / "graph.html")
    body = Path(html).read_text(encoding="utf-8")
    assert "const DATA =" in body and '"id": "a"' in body


def test_viz_holds_50k_nodes(tmp_path: Path) -> None:
    G = Graph()
    for i in range(50_000):
        G.add_node(f"n{i}", label=f"node{i}")
    for i in range(49_999):
        G.add_edge(f"n{i}", f"n{i + 1}")
    comms = {0: [f"n{i}" for i in range(50_000)]}
    labels = {0: "chain"}
    path = write_viz_html(G, comms, labels, tmp_path / "big.html")
    size = Path(path).stat().st_size
    assert size > 2_000_000  # the point: no 5k cap - graph serialized fully


def test_mcp_stdio(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from tests.conftest import build_toy_graph_file

    gpath = build_toy_graph_file(tmp_path)
    proc = subprocess.run(
        [sys.executable, "-m", "nodemonk.mcp", str(gpath)],
        input="\n".join(
            [
                json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}),
                json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/list"}),
                json.dumps({
                    "jsonrpc": "2.0", "id": 3, "method": "tools/call",
                    "params": {"name": "search", "arguments": {"terms": ["alpha"]}},
                }),
            ]
        )
        + "\n",
        capture_output=True,
        text=True,
        timeout=60,
        cwd=str(Path(__file__).parent.parent),
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip().startswith("{")]
    assert proc.returncode == 0
    assert len(lines) >= 3
    init = json.loads(lines[0])
    assert init["result"]["serverInfo"]["name"] == "nodemonk"
    tools = json.loads(lines[1])
    names = {t["name"] for t in tools["result"]["tools"]}
    assert {"search", "query_graph", "shortest_path", "god_nodes"} <= names
    call = json.loads(lines[2])
    text = call["result"]["content"][0]["text"]
    assert "Alpha" in text


def test_server_endpoints_and_react_ui(tmp_path: Path) -> None:
    from io import BytesIO
    from unittest.mock import MagicMock
    from nodemonk.serve import NodeMkHandler
    from tests.conftest import build_toy_graph_file

    gpath = build_toy_graph_file(tmp_path)
    loaded, data = load_graph_file(gpath)
    NodeMkHandler.G = loaded
    NodeMkHandler.DATA = data

    # Test GET / (React app or UI)
    req = MagicMock()
    req.path = "/"
    handler = NodeMkHandler.__new__(NodeMkHandler)
    handler.path = "/"
    handler.rfile = BytesIO()
    handler.wfile = BytesIO()
    handler.send_response = MagicMock()
    handler.send_header = MagicMock()
    handler.end_headers = MagicMock()

    handler.do_GET()
    written = handler.wfile.getvalue().decode("utf-8")
    assert "<!doctype html>" in written.lower()

    # Test GET /api/stats
    handler.path = "/api/stats"
    handler.wfile = BytesIO()
    handler.do_GET()
    stats_data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert stats_data["nodes"] == 3
    assert stats_data["edges"] == 2

    # Test GET /api/hubs
    handler.path = "/api/hubs"
    handler.wfile = BytesIO()
    handler.do_GET()
    hubs_data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert "hubs" in hubs_data

    # Test GET /api/path
    handler.path = "/api/path?a=a&b=b"
    handler.wfile = BytesIO()
    handler.do_GET()
    path_data = json.loads(handler.wfile.getvalue().decode("utf-8"))
    assert path_data["found"] is True

