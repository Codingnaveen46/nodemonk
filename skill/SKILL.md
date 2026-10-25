---
name: nodemonk
description: "Use for any question about a codebase, its architecture, file relationships, or project content — especially when nodemonk-out/ exists, where the question should be treated as a nodemonk query first. Turns any folder of code, docs, papers, images, or videos into a persistent queryable knowledge graph with god nodes, community detection, and query/path/explain tools. No node or result limits."
---

# /nodemonk

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and three outputs: interactive Obsidian-style HTML, GraphRAG-ready JSON, and a plain-language GRAPH_REPORT.md.

## Usage

```
/nodemonk                                    # full pipeline on current directory
/nodemonk <path>                             # full pipeline on specific path
/nodemonk <path> --update                    # incremental - re-extract only new/changed files
/nodemonk <path> --cluster-only              # rerun clustering on existing graph
/nodemonk <path> --cluster-only --resolution 1.5   # more granular communities
/nodemonk <path> --no-viz                    # skip the HTML, just report + JSON
/nodemonk <path> --wiki                      # markdown wiki (index.md + one article per community)
/nodemonk <path> --obsidian                  # Obsidian vault (one note per community)
/nodemonk <path> --svg --graphml --cypher --dot    # extra export formats
/nodemonk add <url>                          # fetch URL into ./raw and update the graph
/nodemonk query "<question>"                 # BFS traversal - broad context
/nodemonk query "<question>" --dfs           # DFS - trace a specific path
/nodemonk path "ModuleA" "ModuleB"           # shortest path between two concepts
/nodemonk explain "ClassName"                # everything connected to one node
/nodemonk search "<terms>"                   # scored node search (id/label/file/docstring)
/nodemonk top --by pagerank --limit 20       # god nodes
/nodemonk stats / community <id> / cycles / bridges / isolated
/nodemonk merge-graphs a.json b.json -o merged.json   # combine graphs
/nodemonk hook install                       # auto-rebuild after every git commit
/nodemonk serve                              # HTTP JSON API + query console
nodemonk mcp                                 # stdio MCP server for agent access
```

## What You Must Do When Invoked

If the user invoked `/nodemonk --help` or `/nodemonk -h` with no other arguments,
print the `## Usage` section above verbatim and stop.

**Zero-install bootstrap (run this if `command -v nodemonk` fails):** never ask
the user to install anything. Run nodemonk ephemerally instead:

```bash
NMK="uvx --from git+https://github.com/Codingnaveen46/nodemonk nodemonk"
$NMK build .            # uv (recommended; caches after first run)
# fallback when uv is absent:
pip install --user git+https://github.com/Codingnaveen46/nodemonk.git && NMK=nodemonk
# or via Docker, no Python needed:
# docker run --rm -v "$(pwd):/workspace" ghcr.io/codingnaveen46/nodemonk:latest build /workspace
```

Use `$NMK` in place of `nodemonk` for every command below.

**Fast path — existing graph:** if `nodemonk-out/graph.json` exists relative to
the current working directory AND the request is a natural-language question
about the codebase (not a rebuild command), skip the build and answer through
the graph:

```bash
nodemonk query "<question>"
nodemonk explain "<concept>"
nodemonk path "<A>" "<B>"
```

**Build path:** otherwise run the pipeline with the detected Python (no LLM,
zero tokens, no node limit):

```bash
python3 -m nodemonk build <path> [--update] [--wiki] [--quiet]
```

Then read `GRAPH_REPORT.md` highlights (god nodes, communities, suggested
questions) and open `nodemonk-out/graph.html` in a browser for the visual.

<!-- nodemonk-skill -->
## nodemonk (knowledge graph)

Build the graph after code changes, and query it before grepping:

```bash
nodemonk build $(pwd)              # full pipeline -> nodemonk-out/graph.html + graph.json + GRAPH_REPORT.md
nodemonk build $(pwd) --update     # incremental: only new/changed files re-extract
nodemonk query "how does the auth flow work?"
nodemonk explain "ClassName"
nodemonk path "ModuleA" "ModuleB"
nodemonk top --by pagerank --limit 20
```

Rules: read `GRAPH_REPORT.md` highlights before exploring; answer codebase
questions through `nodemonk query` / `explain` against `nodemonk-out/graph.json`
instead of re-reading files. Every edge is tagged EXTRACTED / INFERRED /
AMBIGUOUS - trust EXTRACTED, cite AMBIGUOUS with a caveat. No node or query
limit exists; pass --limit only when you want fewer.
<!-- /nodemonk-skill -->
