"""nodemonk.serve - HTTP JSON API + interactive UI over graph.json.

Endpoints (unlimited unless explicit limits):
  GET /                      tiny query console UI
  GET /api/graph.json        full graph file
  GET /api/stats             global stats
  GET /api/search?q=...&kind=&file_glob=&limit=   (limit=0 = unlimited)
  GET /api/node/<id>         node payload
  GET /api/neighbors/<id>?relation=&confidence=
  GET /api/pagerank?limit=
  GET /api/pagerank_top?limit=
  GET /api/gods?by=degree&pagearge... -> then pipe through pagerank or degree
  GET /api/communities/<cid>
  GET /api/path?a=<node>&b=<node>&weighted=
  GET /api/query?question=&mode=bfs|dfs
  GET /api/hubs?by=degree&limit=
  GET /api/cycles?limit
  GET /api/bridges?limit
"""

from __future__ import annotations

import json
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .graph import Graph
from .query import (bfs_subgraph, explain_node, global_stats, neighbor_filter,
                    path_between, resolve_start_nodes, search_nodes)
from .cluster import cohesion_score

_UI = r"""<!doctype html><html><body style="font-family:system-ui;background:#0b0f19;color:#e5e7eb;max-width:780px;margin:40px auto;padding:0 16px">
<h1>nodemonk server</h1>
<p>Graph API is live. Try:</p>
<ul>
<li><a href="../api/stats" style="color:#7cb8ff">/api/stats</a></li>
<li><a href="../api/pagerank?limit=10" style="color:#7cb8ff">/api/pagerank?limit=10</a></li>
<li><a href="../api/hubs?by=degree&limit=10" style="color:#7cb8ff">/api/hubs?by=degree&limit=10</a></li>
<li><a href="../api/search?q=main" style="color:#7cb8ff">/api/search?q=main</a></li>
<li style="margin-top:8px"><a href="query.html" style="color:#7cb8ff">query console</a></li>
</ul>
<p style="color:#9ca3af">All endpoints unlimited: pass <code>limit=0</code> for no cap.</p>
</body></html>"""


_WEB_DIST = Path(__file__).parent / "web_dist"

_MIME_TYPES = {
    ".html": "text/html",
    ".js": "application/javascript",
    ".mjs": "application/javascript",
    ".css": "text/css",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".ico": "image/x-icon",
}


class NodeMkHandler(BaseHTTPRequestHandler):  # noqa: N801
    G: Graph | None = None
    DATA: dict[str, Any] = {}

    def log_message(self, *args: Any) -> None:  # quiet
        pass

    def _send(self, payload: Any, status: int = 200, content_type: str | None = None) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode() if not isinstance(payload, (bytes, str)) else (
            payload.encode() if isinstance(payload, str) else payload
        )
        self.send_response(status)
        if content_type is None:
            content_type = "application/json" if not isinstance(payload, str) or payload.startswith("<") else "text/html"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        parsed = urllib.parse.urlsplit(self.path)
        path = parsed.path.rstrip("/") or "/"
        params = urllib.parse.parse_qs(parsed.query)

        def q(k: str, default: str = "") -> str:
            return (params.get(k, [default]) or [default])[0]

        def qi(k: str, default: int = 0) -> int:
            try:
                return int(q(k, str(default)))
            except (TypeError, ValueError):
                return default

        G = self.G
        if G is None:
            self._send({"error": "graph not loaded"}, 500)
            return

        if path == "/graph.html":
            gh_file = Path("nodemonk-out/graph.html")
            if gh_file.exists():
                self._send(gh_file.read_bytes(), 200, content_type="text/html")
                return

        # Serve static React UI if available
        if _WEB_DIST.exists():
            clean_path = path.lstrip("/")
            file_candidate = _WEB_DIST / clean_path
            if path == "/" or not file_candidate.exists() or file_candidate.is_dir():
                if not path.startswith("/api/"):
                    index_file = _WEB_DIST / "index.html"
                    if index_file.exists():
                        self._send(index_file.read_bytes(), 200, content_type="text/html")
                        return
            elif file_candidate.exists() and file_candidate.is_file():
                suffix = file_candidate.suffix.lower()
                mime = _MIME_TYPES.get(suffix, "application/octet-stream")
                self._send(file_candidate.read_bytes(), 200, content_type=mime)
                return

        if path == "/" or path.endswith("query.html"):
            self._send(_UI)
        elif path == "/api/graph.json":
            self._send(json.dumps(self.DATA, ensure_ascii=False))
        elif path == "/api/stats":
            self._send(global_stats(G))
        elif path == "/api/search":
            self._send({"q": q("q"), "nodes": search_nodes(
                G, [t for t in q("q").split() if t],
                kind=q("kind") or None, file_glob=q("file_glob") or None,
                community=[int(x) for x in q("community", "").split(",") if x] or None,
                limit=qi("limit", 50))})
        elif path.startswith("/api/node/"):
            nid = urllib.parse.unquote(path[len("/api/node/"):])
            self._send(explain_node(G, nid), 200 if "error" not in explain_node(G, nid) else 404)
        elif path.startswith("/api/neighbors/"):
            nid = urllib.parse.unquote(path[len("/api/neighbors/"):])
            self._send(neighbor_filter(G, nid, relation=q("relation") or None, direction=q("direction", "any"), confidence=q("confidence") or None))
        elif path == "/api/pagerank":
            from .analyze import pagerank

            pr = pagerank(G)
            ranked = sorted(pr.items(), key=lambda kv: -kv[1])
            lim = qi("limit", 20)
            self._send({"top": ranked[: lim if lim > 0 else len(ranked)]})
        elif path == "/api/pagerank_top":
            from .analyze import pagerank

            pr = pagerank(G)
            ranked = sorted(pr.items(), key=lambda kv: -kv[1])
            lim = qi("limit", 20)
            out = [{"id": n, "pagerank": s, "label": (G.get_node(n, {}) or {}).get("label", n)} for n, s in ranked[: lim if lim > 0 else len(ranked)]]
            self._send(out)
        elif path == "/api/hubs":
            from .analyze import god_nodes

            self._send({"hubs": god_nodes(G, top_n=qi("limit", 15), by=q("by", "degree"))})
        elif path == "/api/communities":
            comms = (self.DATA.get("communities") or {})
            self._send({"communities": [{"id": int(k), "size": len(v)} for k, v in comms.items()]})
        elif path.startswith("/api/communities/"):
            cid = int(path.rsplit("/", 1)[-1] or 0)
            members = ((self.DATA.get("communities") or {}).get(str(cid)) or [])
            if not members:
                self._send({"error": f"community {cid} not found"}, 404)
                return
            ms = set(members)
            out_reach = sorted({v for m in members for v in G.nbrs(m) if v not in ms})
            self._send({"id": cid, "members": members, "cohesion": cohesion_score(G, members), "out_reach": out_reach[:100]})
        elif path == "/api/path":
            a, b = q("a"), q("b")
            self._send(path_between(G, a, b, weighted=bool(q("weighted", ""))))
        elif path == "/api/query":
            question = q("question")
            starts = resolve_start_nodes(G, question, max_starts=3)
            mode = q("mode", "bfs")
            sub = bfs_subgraph(G, starts, depth=qi("depth", 3)) if mode == "bfs" else explain_uses(G, starts)
            self._send({"question": question, "starts": starts,
                        "nodes": [{"id": n, "label": (G.get_node(n, {}) or {}).get("label", n)} for n in sub["nodes"]],
                        "edges": [{"source": a2, "target": b2, **({"relation": d.get("relation"), "confidence": d.get("confidence")} if isinstance(d, dict) else {})} for a2, b2, d in sub["edges"]]})
        elif path == "/api/cycles":
            from .analyze import find_cycles

            self._send({"cycles": find_cycles(G, limit=qi("limit", 20))})
        elif path == "/api/bridges":
            from .analyze import bridges_and_articulation

            br, art = bridges_and_articulation(G)
            self._send({"bridges": br, "articulation": art})
        else:
            self._send({"error": f"unknown endpoint {path}"}, 404)


def explain_uses(G: Graph, starts: list[str]) -> dict[str, Any]:
    from .query import dfs_subgraph

    return dfs_subgraph(G, starts, depth=6)


def serve_http(graph_path: str, host: str = "127.0.0.1", port: int = 7740) -> None:  # pragma: no cover
    data = json.loads(Path(graph_path).read_text(encoding="utf-8"))
    NodeMkHandler.G = Graph.from_node_link(data)
    NodeMkHandler.DATA = data
    server = ThreadingHTTPServer((host, port), NodeMkHandler)
    print(f"nodemonk::serve -> http://{host}:{port}/  (graph: {graph_path})")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
