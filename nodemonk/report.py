"""nodemonk.report - the honest, plain-language GRAPH_REPORT.md."""

from __future__ import annotations

import datetime as dt
from typing import Any

from . import __version__
from .analyze import confidence_profile
from .graph import Graph


def _fmt_pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def _fmt_num(x: float) -> str:
    return f"{x:,.1f}" if isinstance(x, float) else f"{x:,}"


def generate(
    G: Graph,
    communities: dict[int, list[str]],
    cohesion: dict[int, float],
    labels: dict[int, str],
    gods: list[dict[str, Any]],
    surprises: list[dict[str, Any]],
    detection: dict[str, Any] | None,
    tokens: dict[str, int] | None,
    scan_root: str,
    suggested_questions: list[dict[str, Any]] | None = None,
    metrics: dict[str, Any] | None = None,
) -> str:
    now = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    cats = (detection or {}).get("category_counts", {})
    conf = confidence_profile(G)
    metrics = metrics or {}

    lines: list[str] = []
    a = lines.append

    a(f"# GRAPH_REPORT - nodemonk")
    a("")
    a(f"Generated {now} by nodemonk v{__version__} (zero dependencies, fully local).")
    a("")
    a("## Corpus")
    a("")
    total_files = (detection or {}).get("total_files", 0)
    total_words = (detection or {}).get("total_words", 0)
    a(f"- scanned root: `{scan_root}`")
    a(f"- files: **{total_files:,}** · words: **{total_words:,}**")
    if cats:
        parts = ", ".join(f"{k}: {v}" for k, v in sorted(cats.items(), key=lambda kv: -kv[1]))
        a(f"- categories: {parts}")
    a("")

    a("## Graph")
    a("")
    a(f"- nodes: **{G.number_of_nodes():,}**")
    a(f"- edges: **{G.number_of_edges():,}**")
    mod_str = metrics.get("modularity_str", None)
    a(f"- communities: **{len(communities)}**" + (f" (modularity: {mod_str})" if mod_str else ""))
    if metrics.get("connectivity"):
        a(f"- connectivity: {metrics.get('connectivity')}")
    a("")

    a("## Honesty audit")
    a("")
    a("| confidence | edges |")
    a("|---|---:|")
    for key in ("EXTRACTED", "INFERRED", "AMBIGUOUS"):
        a(f"| {key} | {conf.get(key, 0):,} |")
    a("")
    a("EXTRACTED = explicitly in the source. INFERRED = resolved by nodemonk (e.g. a call across files). AMBIGUOUS = intentionally kept but low-trust.")
    a("")

    a("## Communities")
    a("")
    a("| # | label | size | cohesion |")
    a("|---|---|---:|---:|")
    for cid in sorted(communities):
        members = communities[cid]
        a(f"| {cid} | {labels.get(cid, f'Community {cid}')} | {len(members):,} | {_fmt_pct(cohesion.get(cid, 0.0))} |")
    a("")

    a("## God nodes")
    a("")
    a("Highest-connectivity nodes (structural hubs). All of them, ranked - not capped:")
    a("")
    display = gods[:25]
    if len(gods) > 25:
        a(f"*showing top 25 of {len(gods):,} - run `nodemonk top --limit 200` for more*")
    for row in display:
        src = row.get("source_file") or ""
        degree = row.get("degree", 0)
        line = f"- `{row.get('label')}` ({row.get('file_type') or 'code'})"
        if src:
            line += f" - {src}"
        line += f" - degree **{_fmt_num(degree)}**"
        if "pagerank" in row:
            line += f" - pagerank {_fmt_num(row['pagerank'])}"
        a(line)
    a("")

    a("## Surprising connections")
    a("")
    if surprises:
        for s in surprises:
            a(
                f"- `{s['source_label']}` --{s['relation']}--> `{s['target_label']}` [{s['confidence']}]"
                f" (bridges communities {s['communities'][0]} and {s['communities'][1]})"
            )
    else:
        a("- none detected (every edge stays inside its community)")
    a("")

    a("## Suggested questions")
    a("")
    for q in suggested_questions or []:
        a(f"- {q['question']}")
    a("")

    sugg_stats = {
        k: v for k, v in (metrics or {}).items()
        if k in {"bridges", "articulation", "cycles", "isolated", "resolutions", "ambiguous_scale"}
    }
    if sugg_stats:
        a("## Structural analysis")
        a("")
        for key, val in sugg_stats.items():
            a(f"- **{key}**: {val if not isinstance(val, list) else ', '.join(map(str, val[:12]))}")
        a("")

    a("## Provenance")
    a("")
    a(f"- nodemonk: `{__version__}`")
    a(f"- corpus words: {total_words:,}")
    a(f"- extraction: deterministic AST/structure pass ({(detection or {}).get('detector_version', __version__)})")
    a(f"- cross-file calls resolved: {metrics.get('resolutions', {}).get('symbol_edges', 0):,}")
    a("")

    if tokens:
        a("## Cost")
        a("")
        a(f"- LLM tokens used: input {tokens.get('input', 0):,} · output {tokens.get('output', 0):,}")
        a("")

    a("---")
    a("")
    a("*This graph was built entirely on your machine. Every edge carries its evidence level. Query it, export it, diff it - rereading files is optional.*")
    return "\n".join(lines) + "\n"
