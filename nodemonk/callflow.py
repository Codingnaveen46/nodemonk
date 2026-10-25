"""nodemonk.callflow - Mermaid architecture/call-flow HTML export.

Mirrors graphify's callflow_html: a single self-contained HTML page rendering
the graph as a Mermaid flowchart, grouped by community subgraphs. Nodes are
capped per community for readability; cross-community flows are drawn at the
community level so the diagram stays legible on large graphs.
"""

from __future__ import annotations

import html
import json
from pathlib import Path

from .fsutil import atomic_write
from .graph import Graph

_MERMAX = 2000  # mermaid breaks beyond roughly this many edges


def _mermaid_id(nid: str) -> str:
    out = []
    for ch in nid:
        out.append(ch if (ch.isalnum() or ch == "_") else "_")
    return "n" + "".join(out)


def build_mermaid(
    G: Graph,
    communities: dict[int, list[str]],
    labels: dict[int, str],
    *,
    max_nodes_per_community: int = 25,
) -> str:
    degrees = G.degree_map()
    node_comm: dict[str, int] = {}
    for cid, members in communities.items():
        for m in members:
            node_comm[m] = cid

    lines = ["flowchart LR"]
    emitted: set[str] = set()

    for cid in sorted(communities, key=lambda c: -len(communities[c])):
        members = sorted(communities[cid], key=lambda n: -degrees.get(n, 0))[:max_nodes_per_community]
        label = html.escape((labels.get(cid) or f"Community {cid}"), quote=True)
        lines.append(f"  subgraph C{cid}[\"{label}\"]")
        for nid in members:
            mid = _mermaid_id(nid)
            if mid in emitted:
                continue
            emitted.add(mid)
            nlabel = html.escape(nid, quote=True)
            lines.append(f"    {mid}[\"{nlabel}\"]")
        lines.append("  end")

    # intra-community edges among emitted nodes
    count = 0
    for u, v in G.edges_view():
        if u not in emitted or v not in emitted:
            continue
        if node_comm.get(u) == node_comm.get(v):
            d = G.get_edge_data(u, v, {}) or {}
            rel = str(d.get("relation", "links"))[:20]
            if count < _MERMAX:
                lines.append(f"  {_mermaid_id(u)} -->|{html.escape(rel)}| {_mermaid_id(v)}")
                count += 1

    # collapse cross-community edges into community-level links
    cross: dict[tuple[int, int], int] = {}
    for u, v in G.edges_view():
        cu, cv = node_comm.get(u, -1), node_comm.get(v, -1)
        if cu == cv:
            continue
        key = (min(cu, cv), max(cu, cv))
        cross[key] = cross.get(key, 0) + 1
    for (a, b), cnt in sorted(cross.items(), key=lambda kv: -kv[1])[:80]:
        lines.append(f"  C{a} -.->|{cnt} edges| C{b}")
        count += 1

    return "\n".join(lines)


def to_callflow_html(
    G: Graph,
    communities: dict[int, list[str]],
    labels: dict[int, str],
    out_path: Path,
) -> Path:
    diagram = build_mermaid(G, communities, labels)
    payload = json.dumps({"diagram": diagram}, ensure_ascii=False)
    page = _TEMPLATE.replace("__TITLE__", "nodemonk · call flow").replace("__DIAGRAM__", payload)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write(out_path, page)
    return out_path


_TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__TITLE__</title>
<script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
<style>
  body { margin: 0; background: #0d1117; color: #e6edf3;
         font-family: Inter, system-ui, sans-serif; }
  header { padding: 14px 20px; border-bottom: 1px solid #21262d; }
  h1 { font-size: 15px; margin: 0; font-weight: 600; }
  #graph { padding: 10px 20px 40px; overflow-x: auto; }
  .mermaid { background: #0d1117; }
  .mermaid svg { max-width: none; }
</style></head>
<body>
<header><h1>__TITLE__ — community call flow (cross-community edges collapsed)</h1></header>
<div id="graph"><pre class="mermaid" id="src"></pre></div>
<script>
  const data = __DIAGRAM__;
  document.getElementById('src').textContent = data.diagram;
  mermaid.initialize({ startOnLoad: true, theme: 'dark',
    flowchart: { useMaxWidth: false, htmlLabels: true, curve: 'basis' } });
</script>
</body></html>
"""
