# nodemonk 🧠⚡

> **See everything. Ask anything.** Turn any codebase, documentation, or data corpus into a persistent, queryable knowledge graph with community detection, live graph analytics, and zero arbitrary limits.

[![License: Apache-2.0 OR MIT](https://img.shields.io/badge/License-Apache--2.0%20%7C%20MIT-blue.svg)](LICENSE)
[![Python: >=3.10](https://img.shields.io/badge/Python->=3.10-green.svg)](https://python.org)
[![React: 19](https://img.shields.io/badge/React-19.0-61dafb.svg)](https://react.dev)
[![Zero Dependencies](https://img.shields.io/badge/Dependencies-Zero%20(Pure%20Python)-brightgreen.svg)]()

---

## 📄 License

This project is dual-licensed under the Apache License, Version 2.0, and the MIT License.

You may use this project under either license, at your option.

- Apache License 2.0: [LICENSE](LICENSE)
- MIT License: [LICENSE-MIT](LICENSE-MIT)

This gives users flexibility for both open-source and commercial use while keeping the project clear and trustworthy.

---

## ⚡ Why nodemonk?

`nodemonk` was built to provide a clean, unconstrained, local-first alternative to tools like `graphify`. While `graphify` demonstrated the power of turning code into knowledge graphs, it contains hard limits and brittle dependencies, whereas nodemonk is built for practical engineering work at scale.

### 📊 Concrete Comparison & Evidence

| Feature / Limit | Graphify Labs (`graphify`) | **nodemonk** |
| :--- | :--- | :--- |
| **Node Visualization Limit** | **Hard cap at 5,000 nodes** (`MAX_NODES_FOR_VIZ = 5_000` in `graphify/exporters/html.py:14`; raises `ValueError` if exceeded) | **Unlimited Nodes** (Accelerated custom graph engine with no arbitrary visualization cap) |
| **Query Budget & Truncation** | **Capped at 1,500 tokens** (`--budget 1500`, subagents chunked and truncated) | **Unlimited Queries & Streaming** (`--limit 0` for full traversals, depthless BFS/DFS, and live graph analysis) |
| **Dependencies** | NetworkX, tree-sitter C-bindings, numpy, scipy, graspologic (7-19s JIT import times, fragile compilation) | **Zero External Dependencies** (Pure standard library Python; instant startup) |
| **Call Graph Parked Calls** | **Capped at 64 calls/node** (`_MAX_PARKED_CALLS_PER_NODE = 64` in `extract.py:4515`) | **No Cap** (Full fidelity call and reference capture) |
| **Config & Data File Caps** | Capped: YAML at 1MB/500 pairs, JSON at 1MB, XML at 2MB (`extractors/yaml_config.py:24`) | **Full File Parsing** (Processes enterprise schemas and large monorepos without artificial limits) |
| **Modern React Interface** | Basic single HTML file | **Full React 19 + TypeScript + Vite interactive explorer** built-in |
| **MCP Agent Protocol** | Supported | Supported via `nodemonk mcp` (stdio JSON-RPC compatible with Claude, Cursor, Antigravity, Devin) |
| **Export Ecosystem** | JSON, HTML | JSON, HTML, SVG, DOT, GraphML, Cypher (Neo4j), and Obsidian Vault Markdown with bidirectional `[[wikilinks]]` |

---

## 🚀 Quick Start

### 1. Build a Knowledge Graph
Run `nodemonk build` pointing to any directory (codebase, documentation, or mixed corpus):

```bash
# Build the graph of the current directory
python3 -m nodemonk build .

# Or with custom output folder and extra exports
python3 -m nodemonk build . --out-dir ./nodemonk-out --cypher --obsidian --svg
```

Output generated in `nodemonk-out/`:
- `graph.json`: The complete node-link knowledge graph with explicit confidence metadata.
- `graph.html`: Standalone offline browser visualization (Obsidian-style dot view — works up to any node count).
- `GRAPH_REPORT.md`: Comprehensive architecture audit, community breakdown, God nodes, and suggested questions.
- `wiki/`: (Optional, `--wiki`) Markdown wiki — `index.md` + one article per community.
- `callflow.html`: (Optional, `--callflow`) Mermaid community call-flow diagram.
- `obsidian/`: (Optional) Obsidian vault notes with inter-community wikilinks.
- `cypher.txt`: (Optional) Ready-to-import Cypher statements for Neo4j.

Useful build flags:

```bash
python3 -m nodemonk build . --update          # incremental: only changed files re-extract
python3 -m nodemonk build . --cluster-only    # re-cluster the existing graph
python3 -m nodemonk build . --resolution 1.5  # more, smaller communities
python3 -m nodemonk build . --exclude-hubs 3  # hide the 3 biggest super-hubs from god-node rankings
python3 -m nodemonk build . --no-viz          # skip the HTML, just report + JSON
python3 -m nodemonk merge-graphs a/out/graph.json b/out/graph.json -o merged.json   # cross-repo graphs
```

---

### 2. Install into Your Coding Agent (one command, works like graphify)

`nodemonk install` registers the `/nodemonk` skill with your AI assistant, so typing `/nodemonk .` builds a graph and `/nodemonk query "..."` answers questions through it — no per-assistant manual setup required.

```bash
nodemonk install                 # installs everywhere applicable (see platform list)
nodemonk install --project       # scope to the current repo instead of your user profile
nodemonk install-status          # show what is installed where
nodemonk uninstall               # remove all registrations
nodemonk install --platform zcode --project    # one platform only
```

Supported platforms:

| Assistant | What `nodemonk install` writes | Invocation |
|---|---|---|
| **ZCode** | `~/.zcode/commands/nodemonk.md` (+ Agent-Skills global) | `/nodemonk` |
| **Claude Code** | `~/.claude/skills/nodemonk/SKILL.md` (+ Agent-Skills global) | `/nodemonk` |
| **Codex** | `~/.codex/prompts/nodemonk.md` (+ Agent-Skills global) | `$nodemonk` |
| **GitHub Copilot CLI / VS Code Copilot Chat** | Agent-Skills global + `--project` (`.github/copilot-instructions.md` via AGENTS.md) | ask for nodemonk |
| **OpenCode, Antigravity, Gemini CLI, Cursor, Kilo, Aider, Pi, Devin** | cross-framework Agent-Skills location `~/.agents/skills/nodemonk/SKILL.md` (read by every spec-compliant framework) | `/nodemonk` |
| **Anything with MCP** | `nodemonk mcp` (stdio server, see §4 below) | tools, no slash command |

Once installed, examples your assistant understands:

```
/nodemonk .                                   # build the graph for the current folder
/nodemonk . --wiki                            # also generate the markdown wiki
/nodemonk query "what connects auth to the database?"
/nodemonk path "UserService" "DatabasePool"
/nodemonk explain "RateLimiter"
```

**Keep the graph fresh automatically** — the git hook rebuilds (incrementally, zero tokens) after every commit:

```bash
nodemonk hook install        # post-commit hook; uninstall/status supported
```

### Nothing to install? Run it ephemerally

Like graphify, nodemonk runs without any persistent install. Your agent does this automatically (the skill contains a bootstrap step); humans can use the same one-liners:

```bash
# uv / uvx — run straight from GitHub, cached after first run (recommended)
uvx --from git+https://github.com/Codingnaveen46/nodemonk nodemonk build .
uvx --from git+https://github.com/Codingnaveen46/nodemonk nodemonk query "how does auth work?"

# Docker — no Python at all
docker run --rm -v "$(pwd):/workspace" nodemonk build /workspace
# (build the image once: docker build -t nodemonk https://github.com/Codingnaveen46/nodemonk.git)
```

`nodemonk install` still recommended for daily use — it registers the `/nodemonk` skill so agents bootstrap themselves when the binary is missing.

---

### 3. Launch the Interactive React Web Application
`nodemonk` includes a modern React 19 web interface:

```bash
python3 -m nodemonk serve
```

Open [http://127.0.0.1:7740](http://127.0.0.1:7740) in your browser:
- **Interactive Force Graph**: Pan, zoom, drag, and inspect relationships in real-time.
- **Community Explorer**: Drill down into Louvain-detected communities and cohesion metrics.
- **High-Impact Hubs**: Instant identification of "God Nodes" by PageRank and degree centrality.
- **Shortest Path Finder**: Bidirectional BFS / Dijkstra routing between any two symbols.
- **Query Console**: BFS and DFS traversals answering architectural questions without token limits.
- **Circular Dependency Detection**: Automated Tarjan Strongly Connected Components (SCC) analysis.

To run the React development server with Vite hot reloading:
```bash
cd web
npm install
npm run dev
```

---

### 4. Query from the Terminal
`nodemonk` CLI provides unlimited querying capabilities:

```bash
# Natural-language BFS traversal
python3 -m nodemonk query "how does the pipeline execute"

# Shortest path between two symbols
python3 -m nodemonk path pipeline.py Graph

# List God nodes / architectural hubs
python3 -m nodemonk top --by pagerank --limit 10

# Detect circular dependency loops
python3 -m nodemonk cycles

# Identify bridges and single points of failure
python3 -m nodemonk bridges

# Print global graph metrics
python3 -m nodemonk stats
```

---

### 5. Agent Integration (MCP Server)
`nodemonk` speaks Model Context Protocol (MCP) over stdio. Connect it to Cursor, Claude Code, Devin, or Antigravity:

Add to your MCP configuration:
```json
{
  "mcpServers": {
    "nodemonk": {
      "command": "python3",
      "args": ["-m", "nodemonk.mcp", "/path/to/nodemonk-out/graph.json"]
    }
  }
}
```

Available agent tools:
- `graph_stats`: Inspect graph density, node/edge counts, confidence profile.
- `search`: Fuzzy search across nodes, docstrings, filenames with zero truncation.
- `get_node`: Full node payload and metadata.
- `neighbors`: Directional 1-hop queries filtered by relation type and confidence.
- `query_graph`: Graph traversal from question seed nodes.
- `shortest_path`: Trace the exact route between any two functions or classes.
- `god_nodes`: Retrieve top structural hubs.
- `community`: Detailed community breakdown.
- `cycles`: Circular dependency checks.
- `bridges`: Architectural choke points.

---

## 🛠️ Architecture & Core Modules

```
detect.py  →  extract/  →  build.py  →  cluster.py  →  analyze.py  →  report.py  →  export.py
                                                                         ↓
                                                              serve.py (React UI + HTTP API)
                                                              mcp.py (Agent stdio server)
```

1. **`detect.py`**: Scans files, categorizes code/documents/media, calculates size and word counts.
2. **`extract/`**: Deterministic extractors across Python, TypeScript/JavaScript, Go, Rust, Java, C/C++, Markdown, JSON, YAML, and binary assets.
3. **`graph.py`**: Pure-Python high performance Graph structure with adjacency sets, node indexing, and streaming iterators.
4. **`cluster.py`**: Pure-Python Louvain modularity optimization for automatic community clustering with cohesion scoring.
5. **`analyze.py`**: PageRank, God nodes, Tarjan SCC cycle detection, Hopcroft-Tarjan bridge detection, and graph diffing.
6. **`export.py`**: Universal serializers (JSON, HTML, SVG, DOT, GraphML, Cypher, Obsidian).
7. **`serve.py`**: High-performance HTTP server serving both REST API and compiled React dashboard.
8. **`web/`**: Modern React 19 UI with Vite, Canvas force simulation, and Lucide icons.

---

## 🧪 Testing

Run the test suite with pytest:

```bash
python3 -m pytest
```

---

## 🤝 Contributing

Contributions are welcome — new language extractors, visualization improvements, agent integrations, docs. See [CONTRIBUTING.md](CONTRIBUTING.md) for dev setup, architecture map, and PR guidelines.

---

## 📄 License

Apache License 2.0. Free for open source and commercial use.
