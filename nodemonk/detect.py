"""nodemonk.detect - corpus discovery and sizing.  Unlimited by design:

- walks with os.scandir so giant trees never buffer
- every text category word-counts through a bounded streaming reader
- binary media stays in the corpus but its bytes are never decoded
- hashing/word-count is parallelised with a process pool above 5,000 files
"""

from __future__ import annotations

import os
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any

from .fsutil import read_text_limited
from . import __version__

# ----------------------------------------------------------------------- #
# registries

CODE_EXTS = {
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs", ".mts",
    ".go", ".rs", ".java", ".kt", ".kts", ".rb", ".swift", ".scala", ".cs",
    ".c", ".h", ".cpp", ".c++", ".cc", ".cxx", ".hpp", ".hh", ".hxx",
    ".m", ".mm", ".php", ".zig", ".ex", ".exs", ".erl", ".hrl", ".hs",
    ".lua", ".r", ".R", ".jl", ".dart", ".vue", ".svelte", ".asp", ".aspx",
    ".astro", ".pl", ".pm", ".sh", ".bash", ".zsh", ".fish", ".ps1", ".psm1",
    ".bat", ".cmd", ".sql", ".proto", ".graphql", ".sol", ".pas", ".dpr",
    ".vb", ".vbs", ".elm", ".cl", ".lisp", ".rkt", ".nim", ".groovy",
    ".cmake", ".make", ".mk", ".just", ".nix",
}

DOC_EXTS = {
    ".md", ".markdown", ".mdx", ".txt", ".rst", ".adoc", ".asciidoc",
    ".org", ".jsonl", ".log", ".tex", ".bib",
}

DATA_EXTS = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".csv", ".tsv", ".xml", ".plist", ".env"}

PAPER_EXTS = {".pdf", ".djvu"}

IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico", ".tiff", ".avif", ".heic", ".svg"}

MEDIA_EXTS = {
    ".mp4", ".mov", ".mkv", ".webm", ".avi", ".flv", ".wmv", ".m4v", ".m4a",
    ".mp3", ".wav", ".ogg", ".flac", ".oga", ".opus", ".aac", ".aacp", ".aiff",
    ".mid", ".midi",
}

CATEGORY_BY_EXT: dict[str, str] = {}
for exts, cat in (
    (CODE_EXTS, "code"),
    (DOC_EXTS, "document"),
    (DATA_EXTS, "data"),
    (PAPER_EXTS, "paper"),
    (IMAGE_EXTS, "image"),
    (MEDIA_EXTS, "media"),
):
    for e in exts:
        CATEGORY_BY_EXT[e] = cat

# directories we never walk (build products, vendored trees, tool state) so a
# single monorepo doesn't fold its vendor noise into YOUR project's graph
SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__", ".venv", "venv",
    "env", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", ".mypy",
    "dist", "build", "target", "out", ".next", ".nuxt", ".turbo", ".cache",
    "vendor", "bower_components", ".gradle", "site-packages", ".idea",
    ".vscode", ".macosx", "coverage", ".nyc_output", ".terraform", "cart",
    "nodemonk-out", "graphify-out", ".DS_Store",
}

WORD_COUNT_MAX_BYTES = 6 * 1024 * 1024   # per file, generous for docs & papers
DETECT_POOL_THRESHOLD = 5_000


# ----------------------------------------------------------------------- #

def _classify(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in CODE_EXTS:
        return "code"
    cat = CATEGORY_BY_EXT.get(ext)
    if cat:
        return cat
    return "other"


def _skip_dir(name: str) -> bool:
    if name.startswith(".") and name not in {".github", ".well-known"}:
        return True
    return name in SKIP_DIRS


def _walk(root: Path, max_files: int = 0) -> list[Path]:
    """Collect candidate files. max_files>0 = hard stop after N (safety lock, off by default)."""
    found: list[Path] = []
    stack = [root]
    while stack and (max_files <= 0 or len(found) < max_files):
        current = stack.pop()
        try:
            with os.scandir(current) as it:
                entries = list(it)
        except OSError:
            continue
        entries.sort(key=lambda e: e.name)
        for entry in entries:
            name = entry.name
            if entry.is_dir(follow_symlinks=False):
                if not _skip_dir(name):
                    stack.append(Path(entry.path))
                continue
            if not entry.is_file(follow_symlinks=False):
                continue
            path = Path(entry.path)
            if _classify(path) == "other" and not _readable_maybe(path):
                continue
            found.append(path)
            if max_files and len(found) >= max_files:
                break
    return found


def _readable_maybe(path: Path) -> bool:
    # catch carryless text formats people corpus by hand (Dockerfile, Makefile, LICENSE...)  # noqa: E501
    lower = path.name.lower()
    interesting_prefixes = (
        "dockerfile", "makefile", "license", "readme", "changelog",
        "contributing", "gemfile", "procfile", "vagrantfile", "rakefile",
        "justfile", "cmakelists.txt",
    )
    return lower.startswith(interesting_prefixes) or lower.endswith(tuple([".cfg", ".conf", ".lock"]))


def _hash_and_count(path: Path) -> tuple[str, str, int, int]:
    """sha16, mtime-nanos-truncated, size, words (text categories only)."""
    import hashlib

    h = hashlib.sha256()
    size = 0
    words = 0
    is_binary = _classify(path) in {"image", "media", "paper"} and path.suffix.lower() != ".svg"
    if is_binary:
        try:
            h.update(str(path).encode())
            h.update(str(path.stat().st_mtime_ns).encode())
            size = path.stat().st_size
        except OSError:
            pass
        return h.hexdigest()[:16], "0", size, 0
    truncated = False
    try:
        with open(path, "rb") as fh:
            while True:
                blob = fh.read(1 << 20)
                if not blob:
                    break
                h.update(blob)
                size += len(blob)
                if size <= WORD_COUNT_MAX_BYTES:
                    try:
                        words += len(blob.decode("utf-8", "ignore").split())
                    except (UnicodeDecodeError, MemoryError):
                        words += 0
                else:
                    truncated = True
    except OSError:
        pass
    try:
        mtime = str(path.stat().st_mtime_ns)[:16]
    except OSError:
        mtime = "0"
    if truncated:
        try:
            remaining = path.stat().st_size - WORD_COUNT_MAX_BYTES
            words += int(remaining / 5.5)  # average token-ish word estimate
        except OSError:
            pass
    return h.hexdigest()[:16], mtime, size, words


def _worker(path_str: str) -> tuple[str, str, int, int]:
    return _hash_and_count(Path(path_str))


def detect(root: Path, max_files: int = 0, workers: int | None = None) -> dict[str, Any]:
    root = Path(root).resolve()
    files = _walk(root, max_files=max_files)

    rel_and_info: dict[str, dict[str, Any]] = {}
    total_words = 0

    if len(files) >= DETECT_POOL_THRESHOLD:
        n_workers = max(2, (os.cpu_count() or 4) - 1) if workers is None else max(1, workers)
        with ProcessPoolExecutor(max_workers=n_workers) as pool:
            for path, (sha, mtime, size, words) in zip(files, pool.map(_worker, [str(f) for f in files], chunksize=64)):
                rel = str(path.relative_to(root))
                total_words += words
                rel_and_info[rel] = {
                    "sha": sha, "mtime": mtime, "size": size, "words": words,
                    "category": _classify(path),
                }
    else:
        for f in files:
            sha, mtime, size, words = _hash_and_count(f)
            rel = str(f.relative_to(root))
            total_words += words
            rel_and_info[rel] = {
                "sha": sha, "mtime": mtime, "size": size, "words": words,
                "category": _classify(f),
            }

    by_cat: dict[str, list[int]] = {}
    for info in rel_and_info.values():
        by_cat.setdefault(info["category"], []).append(info["words"])

    grouped: dict[str, list[str]] = {}
    for rel, info in rel_and_info.items():
        grouped.setdefault(info["category"], []).append(rel)

    result = {
        "scan_root": str(root),
        "detector_version": __version__,
        "categories": grouped,
        "files": rel_and_info,
        "total_files": len(rel_and_info),
        "total_words": total_words,
        "category_counts": {c: len(v) for c, v in grouped.items()},
        "warning": None,
    }
    if result["total_files"] == 0:
        result["needs_graph"] = False
    else:
        result["needs_graph"] = True
    return result


def read_words_bounded(path: Path, cap_bytes: int = WORD_COUNT_MAX_BYTES) -> tuple[str, bool]:
    """Read a doc body capping the number of words (used to avoid huge PDFs)."""
    text, truncated = read_text_limited(path, cap_bytes)
    return text, truncated


def top_subdirs(root: Path, limit: int = 5) -> list[tuple[str, int]]:
    """First-level subdirectory of each file path -> file count (for corpus triage)."""
    counts: dict[str, int] = {}
    for rel in _walk(root):
        try:
            parts = Path(rel).relative_to(root).parts
            seg = parts[0] if parts else ""
            counts[seg] = counts.get(seg, 0) + 1
        except ValueError:
            counts["."] = counts.get(".", 0) + 1
    return sorted(counts.items(), key=lambda kv: -kv[1])[:limit]
