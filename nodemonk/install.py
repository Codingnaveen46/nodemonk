"""nodemonk.install - install the /nodemonk skill into AI coding assistants.

Mirrors graphify's installer: one command detects which assistant you run and
registers the skill, so `/nodemonk` (or `$nodemonk` for Codex) works with no
per-assistant setup. Supported platforms:

- ``agents``  cross-framework Agent-Skills spec: ``~/.agents/skills/nodemonk/`` (global)
              or ``./.agents/skills/nodemonk/`` (``--project``). Read by ZCode,
              Claude Code, Codex, Cursor, Gemini CLI, OpenCode, and anything
              else that follows the spec.
- ``zcode``   ``~/.zcode/commands/nodemonk.md`` (global) or ``.zcode/commands/`` (project).
- ``claude``  ``~/.claude/skills/nodemonk/SKILL.md`` or ``.claude/skills/``.
- ``codex``   ``~/.codex/prompts/nodemonk.md`` or ``.codex/prompts/``.

``nodemonk install`` with no --platform installs ``agents`` + ``zcode`` +
``claude`` + ``codex`` (the superset is harmless; assistants ignore what they
don't read). ``nodemonk uninstall`` removes them again.
"""

from __future__ import annotations

import os
from pathlib import Path

from . import __version__

NAME = "nodemonk"

PLATFORMS = ("agents", "zcode", "claude", "codex")

# marketplace-style aliases: assistants that read the Agent-Skills location
PLATFORM_ALIASES = {"antigravity": "agents", "skills": "agents", "opencode": "agents",
                    "cursor": "agents", "gemini": "agents", "kilo": "agents"}

SKILL_RAW_URL = "https://raw.githubusercontent.com/Codingnaveen46/nodemonk/main/skill/SKILL.md"


def skill_markdown() -> str:
    from .hook import SKILL_MARKDOWN_MARKERS

    workflow = SKILL_MARKDOWN_MARKERS.replace("{ROOT}", "$(pwd)").replace("{OUT}", "nodemonk-out")
    return f"""---
name: {NAME}
description: "Use for any question about a codebase, its architecture, file relationships, or project content — especially when nodemonk-out/ exists, where the question should be treated as a nodemonk query first. Turns any folder of code, docs, papers, images, or videos into a persistent queryable knowledge graph with god nodes, community detection, and query/path/explain tools. No node or result limits."
---

# /{NAME}

Turn any folder of files into a navigable knowledge graph with community detection, an honest audit trail, and three outputs: interactive Obsidian-style HTML, GraphRAG-ready JSON, and a plain-language GRAPH_REPORT.md.

## Usage

```
/{NAME}                                    # full pipeline on current directory
/{NAME} <path>                             # full pipeline on specific path
/{NAME} <path> --update                    # incremental - re-extract only new/changed files
/{NAME} <path> --cluster-only              # rerun clustering on existing graph
/{NAME} <path> --cluster-only --resolution 1.5   # more granular communities
/{NAME} <path> --no-viz                    # skip the HTML, just report + JSON
/{NAME} <path> --wiki                      # markdown wiki (index.md + one article per community)
/{NAME} <path> --obsidian                  # Obsidian vault (one note per community)
/{NAME} <path> --svg --graphml --cypher --dot    # extra export formats
/{NAME} add <url>                          # fetch URL into ./raw and update the graph
/{NAME} query "<question>"                 # BFS traversal - broad context
/{NAME} query "<question>" --dfs           # DFS - trace a specific path
/{NAME} path "ModuleA" "ModuleB"           # shortest path between two concepts
/{NAME} explain "ClassName"                # everything connected to one node
/{NAME} search "<terms>"                   # scored node search (id/label/file/docstring)
/{NAME} top --by pagerank --limit 20       # god nodes
/{NAME} stats / community <id> / cycles / bridges / isolated
/{NAME} merge-graphs a.json b.json -o merged.json   # combine graphs
/{NAME} hook install                       # auto-rebuild after every git commit
/{NAME} serve                              # HTTP JSON API + query console
{NAME} mcp                                 # stdio MCP server for agent access
```

## What You Must Do When Invoked

If the user invoked `/{NAME} --help` or `/{NAME} -h` with no other arguments,
print the `## Usage` section above verbatim and stop.

**Zero-install bootstrap (run this if `command -v {NAME}` fails):** never ask
the user to install anything. Run nodemonk ephemerally instead:

```bash
NMK="uvx --from git+https://github.com/Codingnaveen46/{NAME} {NAME}"
$NMK build .            # uv (recommended; caches after first run)
# fallback when uv is absent:
pip install --user git+https://github.com/Codingnaveen46/{NAME}.git && NMK={NAME}
# or via Docker, no Python needed:
# docker run --rm -v "$(pwd):/workspace" ghcr.io/codingnaveen46/{NAME}:latest build /workspace
```

Use `$NMK` in place of `{NAME}` for every command below.

**Fast path — existing graph:** if `nodemonk-out/graph.json` exists relative to
the current working directory AND the request is a natural-language question
about the codebase (not a rebuild command), skip the build and answer through
the graph:

```bash
{NAME} query "<question>"
{NAME} explain "<concept>"
{NAME} path "<A>" "<B>"
```

**Build path:** otherwise run the pipeline with the detected Python (no LLM,
zero tokens, no node limit):

```bash
python3 -m {NAME} build <path> [--update] [--wiki] [--quiet]
```

Then read `GRAPH_REPORT.md` highlights (god nodes, communities, suggested
questions) and open `nodemonk-out/graph.html` in a browser for the visual.

{workflow}
"""


def _write(path: Path, content: str) -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.read_text(encoding="utf-8", errors="replace") == content:
        return f"  = {path} (already current)"
    path.write_text(content, encoding="utf-8")
    return f"  + {path}"


def _remove(path: Path) -> str:
    if path.exists():
        path.unlink()
        try:
            path.parent.rmdir()
        except OSError:
            pass
        return f"  - {path}"
    return f"  = {path} (absent)"


def _targets(platform: str, project: bool) -> list[tuple[str, Path]]:
    home = Path.home()
    md = skill_markdown()
    if project:
        base = Path.cwd()
        return {
            "agents": [("SKILL.md", base / ".agents" / "skills" / NAME / "SKILL.md")],
            "zcode": [("nodemonk.md", base / ".zcode" / "commands" / "nodemonk.md")],
            "claude": [("SKILL.md", base / ".claude" / "skills" / NAME / "SKILL.md")],
            "codex": [("nodemonk.md", base / ".codex" / "prompts" / "nodemonk.md")],
        }[platform]
    return {
        "agents": [("SKILL.md", home / ".agents" / "skills" / NAME / "SKILL.md")],
        "zcode": [("nodemonk.md", home / ".zcode" / "commands" / "nodemonk.md")],
        "claude": [("SKILL.md", home / ".claude" / "skills" / NAME / "SKILL.md")],
        "codex": [("nodemonk.md", home / ".codex" / "prompts" / "nodemonk.md")],
    }[platform]


def install(platform: str = "agents", *, project: bool = False) -> str:
    platform = PLATFORM_ALIASES.get(platform, platform)
    if platform not in PLATFORMS:
        return (f"error: unknown platform '{platform}'. Choose from: {', '.join(PLATFORMS)}"
                f" (aliases: {', '.join(sorted(PLATFORM_ALIASES))})")
    scope = "project" if project else "user"
    lines = [f"installing /{NAME} skill ({platform}, {scope} scope):"]
    for fname, path in _targets(platform, project):
        lines.append(_write(path, skill_markdown()))
    return "\n".join(lines)


def uninstall(platform: str, *, project: bool = False) -> str:
    platform = PLATFORM_ALIASES.get(platform, platform)
    if platform not in PLATFORMS:
        return (f"error: unknown platform '{platform}'. Choose from: {', '.join(PLATFORMS)}"
                f" (aliases: {', '.join(sorted(PLATFORM_ALIASES))})")
    scope = "project" if project else "user"
    lines = [f"uninstalling /{NAME} skill ({platform}, {scope} scope):"]
    for _, path in _targets(platform, project):
        lines.append(_remove(path))
    return "\n".join(lines)


def status() -> str:
    home = Path.home()
    rows = []
    for platform in PLATFORMS:
        for scope, base in (("user", home), ("project", Path.cwd())):
            for _, p in _targets(platform, scope == "project"):
                rows.append((platform, scope, p, p.exists()))
    lines = [f"/{NAME} skill status (nodemonk {__version__}):"]
    for platform, scope, p, present in rows:
        lines.append(f"  [{'x' if present else ' '}] {platform:<7} {scope:<7} {p}")
    hook = Path.cwd() / ".git" / "hooks" / "post-commit"
    if (Path.cwd() / ".git").is_dir():
        from .hook import MARKER_BEGIN

        state = "installed" if hook.exists() and MARKER_BEGIN in hook.read_text(encoding="utf-8", errors="replace") else "not installed"
        lines.append(f"  [{'x' if state == 'installed' else ' '}] git     project  post-commit hook: {state}")
    return "\n".join(lines)


def detect_platform() -> str:
    """Best-effort guess of the assistant running right now (for the hint line)."""
    env = os.environ
    if env.get("ZCODE_ENTRYPOINT") or env.get("CLAUDE_CODE_ENTRYPOINT"):
        return "zcode/claude-code session detected"
    return "unknown"


def no_install_howto(assistant: str = "antigravity") -> str:
    """Marketplace-style install: fetch the skill from GitHub, no nodemonk needed.

    The skill self-bootstraps the nodemonk CLI via uvx on first use, so the
    assistant never needs a local pip install.
    """
    home = Path.home()
    skill_dir = home / ".agents" / "skills" / NAME
    return f"""no-install ({assistant}) — fetch the skill straight from GitHub:

  mkdir -p {skill_dir}
  curl -fsSL {SKILL_RAW_URL} -o {skill_dir}/SKILL.md

Or just tell your assistant, in plain language:

  "Install the nodemonk skill from {SKILL_RAW_URL} into your skills folder."

Restart {assistant} once. From then on /nodemonk (or "use nodemonk to ...")
works, and the skill fetches the nodemonk CLI itself via 'uvx --from
git+https://github.com/Codingnaveen46/nodemonk' on first use — nothing to
install locally. Works identically for any assistant that reads
~/.agents/skills/ (Antigravity, OpenCode, Cursor, Gemini CLI, ...).
"""
