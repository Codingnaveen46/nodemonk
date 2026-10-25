"""nodemonk.wiki - markdown wiki: one article per community + index.md.

Mirrors graphify's wiki export: the knowledge graph rendered as a browsable
set of markdown pages. Every community becomes an article listing its members
with degrees, cross-community connections, and cohesion; index.md lists all
articles ordered by size. Works up to any node count.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .fsutil import atomic_write
from .graph import Graph


def _slug(name: str, cid: int) -> str:
    safe = "".join(c if (c.isalnum() or c in "-_") else "-" for c in name.strip()) or "community"
    return f"{cid:04d}-{safe[:60]}"


def to_wiki(
    G: Graph,
    communities: dict[int, list[str]],
    labels: dict[int, str],
    output_dir: Path,
    *,
    cohesion: dict[int, float] | None = None,
    top_neighbors: int = 15,
) -> Path:
    """Write one markdown article per community plus index.md; return output_dir."""
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    cohesion = cohesion or {}

    degrees = G.degree_map()
    node_comm: dict[str, int] = {}
    for cid, members in communities.items():
        for m in members:
            node_comm[m] = cid

    # cross-community connection index: cid -> {other_cid: count}
    cross: dict[int, dict[int, int]] = {}
    for u, v in G.edges_view():
        cu, cv = node_comm.get(u, -1), node_comm.get(v, -1)
        if cu == cv:
            continue
        cross.setdefault(cu, {})
        cross.setdefault(cv, {})
        cross[cu][cv] = cross[cu].get(cv, 0) + 1
        cross[cv][cu] = cross[cv].get(cu, 0) + 1

    articles: list[tuple[int, str, int]] = []
    for cid in sorted(communities, key=lambda c: -len(communities[c])):
        members = communities[cid]
        label = labels.get(cid) or f"Community {cid}"
        slug = _slug(label, cid)
        coh = cohesion.get(cid)

        lines: list[str] = [
            f"# {label}",
            "",
            f"*Community #{cid} · {len(members)} members"
            + (f" · cohesion {coh * 100:.0f}%" if coh is not None else "")
            + "*",
            "",
        ]

        internal = sorted(members, key=lambda n: -degrees.get(n, 0))
        lines.append("## Members")
        lines.append("")
        lines.append("| Node | Degree | Kind |")
        lines.append("|------|--------|------|")
        for nid in internal:
            nd = G.get_node(nid, {}) or {}
            kind = nd.get("kind") or ""
            lines.append(f"| `{nid}` | {degrees.get(nid, 0)} | {kind} |")
        lines.append("")

        outs = sorted((cross.get(cid) or {}).items(), key=lambda kv: -kv[1])[:top_neighbors]
        if outs:
            lines.append("## Connected communities")
            lines.append("")
            lines.append("| Community | Shared edges |")
            lines.append("|-----------|--------------|")
            for other, cnt in outs:
                olabel = labels.get(other) or f"Community {other}"
                lines.append(f"| [{olabel}](./{_slug(olabel, other)}.md) | {cnt} |")
            lines.append("")

        # intra-community bridges: members linking to members of other communities
        boundary: dict[str, int] = {}
        for nid in members:
            for nbr in G.nbrs(nid):
                if node_comm.get(nbr, -1) != cid:
                    boundary[nid] = boundary.get(nid, 0) + 1
        if boundary:
            top_bridge = sorted(boundary.items(), key=lambda kv: -kv[1])[:10]
            lines.append("## Boundary nodes (bridging outward)")
            lines.append("")
            for nid, cnt in top_bridge:
                lines.append(f"- `{nid}` — {cnt} external connection(s)")
            lines.append("")

        atomic_write(output_dir / f"{slug}.md", "\n".join(lines))
        articles.append((cid, label, len(members)))

    index: list[str] = [
        "# nodemonk wiki",
        "",
        f"{len(articles)} communities, {G.number_of_nodes():,} nodes, {G.number_of_edges():,} edges.",
        "",
        "| Community | Size | Article |",
        "|-----------|------|---------|",
    ]
    for cid, label, size in articles:
        index.append(f"| {label} | {size} | [#{cid}](./{_slug(label, cid)}.md) |")
    atomic_write(output_dir / "index.md", "\n".join(index) + "\n")
    return output_dir
