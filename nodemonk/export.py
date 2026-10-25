"""nodemonk.export - graph.json, graph.html, SVG, GraphML, Cypher, DOT, Obsidian."""

from __future__ import annotations

import json
import re
import xml.sax.saxutils as sx
from pathlib import Path
from typing import Any

from . import __version__, SCHEMA_VERSION
from .fsutil import atomic_write
from .graph import Graph
from .viz import write_viz_html, _PALETTE

CONF_RANK = {"EXTRACTED": 0, "INFERRED": 1, "AMBIGUOUS": 2}


# --------------------------------------------------------------------- #
# json

def to_json(
    G: Graph,
    communities: dict[int, list[str]],
    labels: dict[int, str],
    output_path: Path,
    *,
    meta: dict[str, Any] | None = None,
    hyperedges: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Node-link graph + communities + labels + meta. Stable, deduped, direction kept."""
    node_comm: dict[str, int] = {}
    for cid, members in communities.items():
        for m in members:
            node_comm[m] = cid

    nodes: list[dict[str, Any]] = []
    for nid, nd in G.nodes_data():
        nd_out = {"id": nid, **{k: v for k, v in nd.items() if k != "id"}}
        nd_out["community"] = node_comm.get(nid)
        nodes.append(nd_out)
    nodes.sort(key=lambda n: (str(n.get("source_file") or ""), n["id"]))

    best: dict[tuple[str, str, str], dict[str, Any]] = {}
    for u, v in G.edges_view():
        d = G.get_edge_data(u, v, {}) or {}
        rel = str(d.get("relation", ""))
        key = (
            (u, v, rel) if (G.is_directed() or u < v) else (v, u, rel)
        )
        conf_new = CONF_RANK.get(str(d.get("confidence")), 2)
        cur = best.get(key)
        conf_cur = CONF_RANK.get(str(cur.get("confidence")), 2) if cur else 99
        if cur is None or conf_new < conf_cur:
            best[key] = {
                "source": key[0],
                "target": key[1],
                "relation": rel,
                "confidence": str(d.get("confidence", "EXTRACTED")),
                "confidence_score": float(d.get("confidence_score", 1.0)),
                "weight": float(d.get("weight", 1.0)),
                "directed": G.is_directed(),
            }
    links = [best[k] for k in sorted(best)]

    payload = {
        "graph": {
            "schema_version": SCHEMA_VERSION,
            "nodemonk_version": __version__,
            "directed": G.is_directed(),
            "multigraph": False,
            "node_count": len(nodes),
            "edge_count": len(links),
        },
        **(meta or {}),
        "nodes": nodes,
        "links": links,
        "communities": {str(cid): members for cid, members in sorted(communities.items())},
        "community_labels": {str(cid): labels.get(cid, f"Community {cid}") for cid in sorted(communities)},
    }
    if hyperedges:
        payload["hyperedges"] = hyperedges
    atomic_write(Path(output_path), json.dumps(payload, ensure_ascii=False, indent=1))
    return payload


def load_graph_file(path: Path) -> tuple[Graph, dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    G = Graph.from_node_link(data)
    return G, data


# --------------------------------------------------------------------- #
# svg (deterministic community ring layout - no physics)

def to_svg(
    G: Graph,
    communities: dict[int, list[str]],
    labels: dict[int, str],
    output_path: Path,
    width: int = 1800,
    height: int = 1400,
) -> Path:
    node_comm: dict[str, int] = {}
    for cid, members in communities.items():
        for m in members:
            node_comm[m] = cid
    cids = sorted(communities)
    rings: dict[int, float] = {cid: 0.62 * min(width, height) * (0.25 + i) / max(len(cids), 4) for i, cid in enumerate(cids)}
    cids_sorted = sorted(communities, key=lambda c: -len(communities[c]))
    pos: dict[str, tuple[float, float]] = {}
    for i, cid in enumerate(cids_sorted):
        members = communities[cid]
        members = sorted(members)
        n = len(members)
        radius = rings.get(cid, 120) * (0.6 + 0.65 * len(cids_sorted) / max(len(cids_sorted), 1))
        radius = 90 + 40 * (i + 1)
        cx = width / 2 + radius * 1.15 * ((-1) ** (i % 3) * (i // 2 + 1)) if i else width / 2
        cy = height / 2 + 90 * i if i else height / 2
        ang = 0.0
        for j, m in enumerate(members):
            ang = 2 * 3.14159 * j / max(n, 1)
            pos[m] = (cx + radius * 0.62 * mathr(ang), cy + radius * 0.55 * mathr(ang + 1.57))
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" fill="#0b0f19"/>',
    ]
    degrees = G.degree_map()
    for u, v in G.edges_view():
        pu, pv = pos.get(u), pos.get(v)
        if not pu or not pv:
            continue
        conf = (G.get_edge_data(u, v, {}) or {}).get("confidence", "EXTRACTED")
        stroke = {"EXTRACTED": "#38bdf8", "INFERRED": "#6366f1", "AMBIGUOUS": "#f59e0b"}.get(conf, "#334155")
        parts.append(
            f'<line x1="{pu[0]:.1f}" y1="{pu[1]:.1f}" x2="{pv[0]:.1f}" y2="{pv[1]:.1f}" stroke="{stroke}" stroke-opacity="0.18" />'
        )
    i = 0
    for nid, (x, y) in pos.items():
        nd = G.get_node(nid, {}) or {}
        cid = node_comm.get(nid, -1)
        color = _PALETTE[cid % len(_PALETTE)] if cid >= 0 else "#6b7280"
        r = 2 + 6 * (degrees.get(nid, 0) / max(max(degrees.values(), default=1), 1)) ** 0.5
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.1f}" fill="{color}"/>')
        i += 1
        if i < 400 and degrees.get(nid, 0) >= 2:
            parts.append(
                f'<text x="{x + r + 2:.1f}" y="{y + 3:.1f}" font-size="9" fill="#9ca3af">{sx.escape(str(nd.get("label", nid))[:38])}</text>'
            )
    parts.append("</svg>")
    atomic_write(Path(output_path), "\n".join(parts))
    return Path(output_path)


def mathr(angle: float) -> float:
    import math as _m

    return _m.sin(angle)


# --------------------------------------------------------------------- #
# graphml + cypher + dot

def _xml_clean(value: Any) -> str:
    return sx.escape(str(value))


def to_graphml(G: Graph, output_path: Path) -> Path:
    keys = [
        ('node', 'label', 'string'), ('node', 'file_type', 'string'),
        ('node', 'source_file', 'string'), ('node', 'community', 'string'),
        ('edge', 'relation', 'string'), ('edge', 'confidence', 'string'),
        ('edge', 'weight', 'double'),
    ]
    out = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<graphml xmlns="http://graphml.graphdrawing.org/xmlns">',
        *[f'<key id="{k[1]}" for="{k[0]}" attr.name="{k[1]}" attr.type="{k[2]}"/>' for k in keys],
        '<graph id="nodemonk" edgedefault="undirected">' if not G.is_directed() else '<graph id="nodemonk" edgedefault="directed">',
    ]
    node_comm: dict[str, int] = {}
    for nid, nd in G.nodes_data():
        out.append(f'  <node id="{_xml_clean(nid)}">')
        for key in keys:
            if key[0] != "node":
                continue
            val = nd.get(key[1])
            if val is not None:
                out.append(f'    <data key="{key[1]}">{_xml_clean(val)}</data>')
        out.append('  </node>')
    for u, v in G.edges_view():
        d = G.get_edge_data(u, v, {}) or {}
        out.append('  <edge source="%s" target="%s">' % (_xml_clean(u), _xml_clean(v)))
        for key in keys:
            if key[0] != "edge":
                continue
            if key[1] in d:
                out.append(f'    <data key="{key[1]}">{_xml_clean(d.get(key[1]))}</data>')
        out.append('  </edge>')
    out.append('</graph>')
    out.append('</graphml>')
    atomic_write(Path(output_path), "\n".join(out))
    return Path(output_path)


def _cypher_escape(s: Any) -> str:
    return json.dumps(str(s), ensure_ascii=False)


def to_cypher(G: Graph, output_path: Path) -> Path:
    """Neo4j import file: MERGE idempotent, safe to re-run."""
    lines = [":begin"]
    for nid, nd in G.nodes_data():
        props = {
            "id": nid,
            "label": str(nd.get("label", nid)),
            "file_type": str(nd.get("file_type", "code")),
        }
        if nd.get("source_file"):
            props["source_file"] = str(nd["source_file"])
        props_s = ", ".join(f"{k}: {_cypher_escape(v)}" for k, v in props.items())
        lines.append(f"MERGE (n:NmNode {{{props_s}}});")
    for u, v in G.edges_view():
        d = G.get_edge_data(u, v, {}) or {}
        rel = re.sub(r"[^A-Za-z0-9_]", "_", str(d.get("relation", "linked"))) or "LINKED"
        rel = rel.upper() if not rel.isupper() else rel.capitalize()
        weight = float(d.get("weight", 1.0))
        conf = str(d.get("confidence", "EXTRACTED"))
        lines.append(
            f"MATCH (a:NmNode {{id: {_cypher_escape(u)}}}), (b:NmNode {{id: {_cypher_escape(v)}}}) "
            f"MERGE (a)-[r:{rel}]->(b) SET r.confidence={_cypher_escape(conf)}, r.weight={weight};"
        )
    lines.append(":commit")
    atomic_write(Path(output_path), "\n".join(lines))
    return Path(output_path)


def to_dot(G: Graph, output_path: Path) -> Path:
    node_comm: dict[str, int] = {}
    lines = ["graph nodemonk {" if not G.is_directed() else "digraph nodemonk {", "  rankdir=LR;", '  node [shape=box style=filled fillcolor="#1f2937" fontcolor="#e5e7eb" fontsize=10];']
    for nid, nd in G.nodes_data():
        color = _PALETTE[node_comm.get(nid, 0) % len(_PALETTE)] if node_comm.get(nid, 0) >= 0 else "#334155"
        lines.append(f'  "{_dot_escape(nid)}" [label="{_dot_escape(str(nd.get("label", nid))[:60])}" fillcolor="{color}"];')
    for u, v in G.edges_view():
        d = G.get_edge_data(u, v, {}) or {}
        lines.append(f'  "{_dot_escape(u)}" {"->" if G.is_directed() else "--"} "{_dot_escape(v)}" [label="{_dot_escape(str(d.get("relation", "")))}"];')
    lines.append("}")
    atomic_write(Path(output_path), "\n".join(lines))
    return Path(output_path)


def _dot_escape(s: str) -> str:
    return s.replace('\\', '\\\\').replace('"', '\\"')


# --------------------------------------------------------------------- #
# Obsidian vault - one note per COMMUNITY (unlimited, unlike per-node vaults)

_COMM_TAG = "nodemonk"


def _obsidian_tag(name: str) -> str:
    return "nm-" + re.sub(r"[^\w-]+", "-", name.lower()).strip("-")[:48]


def _yaml_str(s: str) -> str:
    s = str(s or "")
    if re.search(r"[:#\"'\[\]{}&*!|>%@`]", s) or s != s.strip():
        import json as _j

        return _j.dumps(s, ensure_ascii=False)
    return s


def _link_target(label: str) -> str:
    return "[[" + re.sub(r"[\[\]|#^]", "", label)[:120] + "]]"


def to_obsidian(
    G: Graph,
    communities: dict[int, list[str]],
    labels: dict[int, str],
    output_dir: Path,
    cohesion: dict[int, float] | float | None = None,
) -> int:
    node_comm: dict[str, int] = {}
    for cid, ms in communities.items():
        for m in ms:
            node_comm[m] = cid
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    if isinstance(cohesion, (int, float)):
        cohesion_map: dict[int, float] = {cid: float(cohesion) for cid in communities}
    elif isinstance(cohesion, dict):
        cohesion_map = cohesion
    else:
        cohesion_map = {}

    index_links = []
    written = 0
    for cid in sorted(communities):
        members = communities[cid]
        label = labels.get(cid, f"Community {cid}")
        slug = re.sub(r"[^\w-]+", "-", label.strip().lower().replace(" ", "-"))[:40] or "unknown"
        file_name = f"community-{cid:04d}-{slug}.md"
        rel_nodes = sorted(members, key=lambda n: -G.degree(n))
        member_lines = []
        for nid in rel_nodes[:400]:
            nd = G.get_node(nid, {}) or {}
            extra = f" ({nd.get('file_type')})" if nd.get("file_type") else ""
            member_lines.append(f"- {_link_target(str(nd.get('label') or nid))} {extra}")
        if len(rel_nodes) > 400:
            member_lines.append(f"- … {len(rel_nodes) - 400} more members")
        outbound = pairs = 0
        seen_out: list[str] = []
        for nid in rel_nodes:
            for v in G.nbrs(nid):
                if v not in set(members) and v not in seen_out:
                    seen_out.append(v)
        lines = [
            f"# {label}",
            "",
            f"- id: {cid}",
            f"- size: {len(members)}",
            f"- cohesion: {cohesion_map.get(cid, 0.0) * 100:.1f}%",
            f"- tags: #{_COMM_TAG}-{cid}, #community",
            "",
            "## Members",
            *member_lines,
            "",
            "## Outside reach (members connect out to)",
        ]
        lines.extend(f"- {_link_target(s)}" for s in sorted(seen_out)[:200])
        atomic_write(out / file_name, "\n".join(lines) + "\n")
        index_links.append(
            f"[[{file_name[:-3]}|{label}]] - {len(members)} nodes · cohesion {cohesion_map.get(cid, 0.0) * 100:.0f}%"
        )
        written += 1

    overview = [
        "# nodemonk overview",
        "",
        f"- nodes: {G.number_of_nodes():,}",
        f"- edges: {G.number_of_edges():,}",
        f"- communities: {len(communities)}",
        f"- built by: nodemonk {__version__}",
        "",
        "## Communities",
        *sorted(index_links),
        "", "",
        "Open this folder as an Obsidian vault; use the graph view for a community-colored map.",
    ]
    atomic_write(out / "00-index.md", "\n".join(overview) + "\n")
    return written + 1
