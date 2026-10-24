"""nodemonk.ingest - URL capture into the corpus (http/https only, size-capped).

Supported: any webpage (converted lossy to markdown-ish text), pdf (raw),
arxiv (abstract markdown built from the pdf text heuristics), images (raw).
Author/contributor metadata is stored in frontmatter so the extractor copies
it onto nodes.
"""

from __future__ import annotations

import datetime as dt
import html as pyhtml
import re
from pathlib import Path

from .security import validate_url, fetch_limited, SecurityError

_UTILITY_TAGS = re.compile(r"<(script|style|svg|noscript)[^>\v]*>.*?</\1>", re.I | re.S)
_BLOCK_BREAKS = re.compile(r"</(p|div|section|h[1-6]|li|tr|article|blockquote)>", re.I)
_BREAK_TAGS = re.compile(r"<br\s*/?a?>", re.I)
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
_TAGS = re.compile(r"<[^>]+>")


def html_to_text(raw: bytes) -> tuple[str, str]:
    """Very small lossy HTML -> text conversion; returns (title, body)."""
    html = raw.decode("utf-8", "replace")
    title_m = _TITLE_RE.search(html)
    title = pyhtml.unescape(title_m.group(1)).strip() if title_m else "untitled"
    html = _UTILITY_TAGS.sub("", html)
    html = _BLOCK_BREAKS.sub("\n\n", html)
    html = _BREAK_TAGS.sub("\n", html)
    html = re.sub(r"<h([1-6])[^>]*>", lambda m: "\n" + "#" * int(m.group(1)) + " ", html, flags=re.I)
    text = _TAGS.sub(" ", html)
    text = pyhtml.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return title, text.strip()


def ingest(url: str, target_dir: Path, *, author: str | None = None, contributor: str | None = None) -> Path:
    url = validate_url(url)
    try:
        blob, _truncated = fetch_limited(url)
    except SecurityError:
        raise
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"download failed for {url}: {exc}") from exc

    suffix = ".pdf" if ".pdf" in url.lower().split("?")[0] else (
        ".png" if ".png" in url.lower().split("?")[0] else
        ".jpg" if (".jpg" in url.lower().split("?")[0] or ".jpeg" in url.lower().split("?")[0]) else
        ".md"
    )
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%d-%H%M%S")
    from urllib.parse import urlsplit

    host = urlsplit(url).netloc.replace(":", "-")
    stem = re.sub(r"[^\w.-]+", "-", urlsplit(url).path.rsplit("/", 1)[-1] or "page")[:80] or "page"
    out = Path(target_dir) / f"{stem}-{stamp}{suffix}"
    out.parent.mkdir(parents=True, exist_ok=True)

    fm = [
        "---",
        f"source_url: {json_quote(url)}",
        f"captured_at: {dt.datetime.now(dt.UTC).isoformat()}",
    ]
    if author:
        fm.append(f"author: {json_quote(author)}")
    if contributor:
        fm.append(f"contributor: {json_quote(contributor)}")
    fm.append("---")

    if suffix in {".md"}:
        title, text = html_to_text(blob)
        body = f"# {title}\n\n{text}\n"
        out.write_text("\n".join(fm) + "\n\n" + body, encoding="utf-8")
    else:
        out.write_bytes(blob)
    return out


def json_quote(s: str) -> str:
    import json as _j

    return _j.dumps(s, ensure_ascii=False)
