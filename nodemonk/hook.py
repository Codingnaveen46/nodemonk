"""nodemonk.hook - git post-commit hook that keeps the graph fresh.

Only code changes are handled instantly (deterministic, no LLM): the hook runs
`nodemonk build <repo-root> --update --code-only` which does ABI hashing + AST
extraction + rebuild. Doc changes land the next time you run `--update` yourself.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

MARKER_BEGIN = "# >>> nodemonk hook >>>"
MARKER_END = "# <<< nodemonk hook <<<"

SKILL_MARKDOWN_MARKERS = """<!-- nodemonk-skill -->
## nodemonk (knowledge graph)

Build the graph after code changes, and query it before grepping:

```bash
nodemonk build {ROOT}              # full pipeline -> {OUT}/graph.html + graph.json + GRAPH_REPORT.md
nodemonk build {ROOT} --update     # incremental: only new/changed files re-extract
nodemonk query "how does the auth flow work?"
nodemonk explain "ClassName"
nodemonk path "ModuleA" "ModuleB"
nodemonk top --by pagerank --limit 20
```

Rules: read `GRAPH_REPORT.md` highlights before exploring; answer codebase
questions through `nodemonk query` / `explain` against `{OUT}/graph.json`
instead of re-reading files. Every edge is tagged EXTRACTED / INFERRED /
AMBIGUOUS - trust EXTRACTED, cite AMBIGUOUS with a caveat. No node or query
limit exists; pass --limit only when you want fewer.
<!-- /nodemonk-skill -->"""


def hook_block(repo_root: Path | None = None) -> str:
    nmk = os.environ.get("NODEMONK_BIN", "nodemonk")
    code = f"""{MARKER_BEGIN}
# keep your knowledge graph fresh after every commit (code changes only; docs need manual --update)
if command -v "$NODEMONK_BIN" >/dev/null 2>&1; then
  ROOT="$(git rev-parse --show-toplevel 2>/dev/null)"
  [ -n "$ROOT" ] && "$NODEMONK_BIN" build "$ROOT" --update --code-only --quiet >/dev/null 2>&1 || true
fi
{MARKER_END}
"""
    return code


def _find_post_commit(repo_root: Path) -> Path:
    return repo_root / ".git" / "hooks" / "post-commit"


def install(repo_root: Path) -> str:
    if not (repo_root / ".git").is_dir():
        return f"not a git repository: {repo_root}"
    hook = _find_post_commit(repo_root)
    existing = hook.read_text(encoding="utf-8", errors="replace") if hook.exists() else ""
    if MARKER_BEGIN in existing:
        return "nodemonk hook already installed"
    probe = 'NODEMONK_BIN="$(command -v nodemonk || true)"; '
    code = probe + hook_block(repo_root)
    prefix = existing.rstrip().rstrip("#") if existing.strip() else ""
    hook.parent.mkdir(parents=True, exist_ok=True)
    hook.write_text(("\n" + prefix.rstrip() + "\n" if prefix else "") + code, encoding="utf-8")
    hook.chmod(os_mode(hook) | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return f"post-commit hook installed in {hook}"


def os_mode(path: Path) -> int:
    try:
        return stat.S_IMODE(path.stat().st_mode)
    except OSError:
        return 0o644


def uninstall(repo_root: Path) -> str:
    hook = _find_post_commit(repo_root)
    if not hook.exists():
        return "no hook file (nothing to remove)"
    existing = hook.read_text(encoding="utf-8", errors="replace")
    if MARKER_BEGIN not in existing:
        return "nodemonk hook not installed"
    start = existing.index(MARKER_BEGIN)
    end = existing.index(MARKER_END) + len(MARKER_END)
    cleaned = (existing[:start] + existing[end:]).rstrip("\n")
    if cleaned.strip():
        hook.write_text(cleaned + "\n", encoding="utf-8")
    else:
        hook.unlink()
    return "nodemonk hook removed"


def status(repo_root: Path) -> str:
    hook = _find_post_commit(repo_root)
    if not hook.exists():
        return "not installed"
    return "installed" if MARKER_BEGIN in hook.read_text(encoding="utf-8", errors="replace") else "not installed"
