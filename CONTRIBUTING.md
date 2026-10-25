# Contributing to nodemonk

Thanks for your interest in improving nodemonk! This guide covers everything needed to get a dev environment running and land a contribution.

## Development setup

nodemonk is deliberately **pure standard-library Python** (zero runtime dependencies) with a React 19 web frontend. Requirements: Python >= 3.10, Node.js >= 18 (only for frontend work).

```bash
git clone https://github.com/Codingnaveen46/nodemonk.git
cd nodemonk

# Python: install in editable mode with dev tools
python3 -m venv .venv && source .venv/bin/activate
pip install -e . pytest

# Web frontend (only needed when touching web/ or nodemonk/web_dist)
cd web && npm install && cd ..
```

## Verifying your changes

```bash
python3 -m pytest                 # full test suite (31 tests, must pass)
python3 -m pytest tests/test_extractors.py -q   # one file

# Rebuild the bundled single-file UI after editing web/src/**
cd web && npm run build && cd ..  # emits ../nodemonk/web_dist/index.html

# Regenerate a graph to eyeball behavior end-to-end
python3 -m nodemonk build . --out /tmp/nmk-test
python3 -m nodemonk serve         # React UI at http://127.0.0.1:7740
```

CI expectations: tests pass, `web_dist/index.html` is rebuilt if (and only if) `web/src/**` changed, and no screenshots/logs or `nodemonk-out/` output are committed (see `.gitignore`).

## Where things live

```
nodemonk/
  detect.py       corpus scan + categorization
  extract/        language extractors (one module per language family)
  build.py        extraction dict -> Graph
  graph.py        the pure-Python Graph structure
  cluster.py      Louvain communities + cohesion
  analyze.py      pagerank, god nodes, cycles, bridges, graph diff
  pipeline.py     the build orchestrator (flags land here)
  cli.py          command surface
  export.py       JSON/SVG/DOT/GraphML/Cypher/Obsidian serializers
  viz.py          graph.html writer (embeds web_dist + data)
  wiki.py         --wiki markdown wiki
  callflow.py     --callflow Mermaid HTML
  install.py      /nodemonk skill installer for AI assistants
  hook.py         git post-commit hook
  serve.py, mcp.py HTTP API / React UI host, stdio MCP server
web/              React 19 + Vite source for the explorer
nodemonk/web_dist compiled single-file bundle (committed; consumed by viz.py)
```

## Common contributions

### Add a language extractor

1. Create `nodemonk/extract/<lang>.py` with an `extract_<lang>(path) -> {"nodes": [...], "edges": [...]}` function. Nodes: `{id, label, source_file, source_location?, kind?}`. Edges: `{source, target, relation, confidence: EXTRACTED|INFERRED|AMBIGUOUS}`.
2. Register the file suffix in the dispatch table in `nodemonk/extract/__init__.py`.
3. Add tests + a fixture under `tests/`.
4. Run the suite and a real build against a repo in that language.

### Touch the visualizer

`web/src/components/GraphCanvas.tsx` renders everything on canvas with batched `Path2D` buckets, a spatial hash for hit tests, and LOD gates. The Obsidian dot view must stay label-budgeted and glow-restricted so 50k+ node graphs stay smooth — benchmark with a large graph before/after (`python3 -m nodemonk build <big-repo>`).

### Improve the agent integrations

`nodemonk/install.py` writes skill files; `nodemonk/mcp.py` is the stdio MCP server. Keep the MCP tool output shape stable — agents depend on it.

## Pull requests

1. Branch from `main` (`feat/...` or `fix/...`).
2. Keep PRs focused: one feature or fix per PR, with tests.
3. Describe **what** changed and **why**; include before/after output for CLI-visible changes.
4. Commit messages: imperative mood, e.g. `feat(cluster): resolution-scaled label propagation`.

## Code style

- Python: stdlib only at runtime, type hints, module docstring at top (`"""nodemonk.x - ..."""`), no new heavy dependencies without discussion.
- TypeScript/React: match the existing inline-style + hooks patterns in `web/src`.
- Everything user-facing is **unlimited by default** — never add a truncation cap without a `--limit` opt-in.

## Reporting issues

Open a GitHub issue with: the command you ran, the unexpected output, Python version, and (if possible) a minimal corpus that reproduces it. Never paste proprietary code into an issue.

## License

By contributing you agree your contributions are licensed under the Apache License 2.0.
