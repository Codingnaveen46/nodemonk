"""Security primitives.  All external input passes through here."""

from __future__ import annotations

import os
import re
import urllib.parse
import urllib.request
from pathlib import Path

_ALLOWED_SCHEMES = ("http", "https")
_URL_RE = re.compile(r"^https?://", re.I)
_FETCH_MAX_BYTES = 25 * 1024 * 1024  # 25 MB cap, overridable via env
_CTRL_CHARS_RE = re.compile(r"[\x00-\x1f\x7f]")


class SecurityError(Exception):
    pass


def validate_url(raw: str) -> str:
    url = (raw or "").strip()
    if not url or not _URL_RE.match(url):
        raise SecurityError(f"only http(s) URLs are supported: {raw!r}")
    parsed = urllib.parse.urlsplit(url)
    if parsed.scheme.lower() not in _ALLOWED_SCHEMES:
        raise SecurityError("only http(s) schemes allowed")
    if not parsed.netloc:
        raise SecurityError("URL must contain a host")
    # NOTE: we allow but refuse to set credentials; strip user:pass to avoid leakage downstream
    netloc = parsed.netloc.split("@")[-1]
    rebuilt = urllib.parse.SplitResult("", netloc, parsed.path, parsed.query, "").geturl()
    return rebuilt or url


_NOFILE_REDIRECT = urllib.request.HTTPRedirectHandler()


def validate_graph_path(root_out: Path, target: Path) -> Path:
    resolved = (target if target.is_absolute() else root_out / target).resolve()
    out_root = Path(root_out).resolve()
    if out_root != resolved and out_root not in resolved.parents:
        raise SecurityError(f"path escapes {root_out}: {target}")
    return resolved


def sanitize_label(label: str | None, cap: int = 256) -> str:
    text = _CTRL_CHARS_RE.sub("", str(label or ""))
    return text[:cap].strip()


def fetch_limited(url: str, max_bytes: int | None = None, timeout: float = 30.0) -> tuple[bytes, bool]:
    """GET url, hard size-capped so a rogue server can't fill the disk."""
    cap = max_bytes or int(os.environ.get("NODEMONK_FETCH_MAX", _FETCH_MAX_BYTES))
    req = urllib.request.Request(
        url, headers={"User-Agent": "nodemonk/1.0", "Accept": "*/*"}
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (scheme validated upstream)
        data = resp.read(cap + 1)
    if len(data) > cap:
        return data[:cap], True
    return data, False
