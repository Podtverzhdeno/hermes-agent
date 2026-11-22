from __future__ import annotations

"""Read-only file MCP template. Configure a dedicated non-sensitive MCP_FILE_ROOT.

This prevents obvious path traversal and unbounded file reads. It does not
provide OS-level sandboxing or eliminate concurrent filesystem TOCTOU races.
For hostile local workspaces, isolate the server under a restricted OS account.
"""

import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP


mcp = FastMCP("__SERVER_NAME__")

MAX_FILE_BYTES = 1_048_576
MAX_PREVIEW_CHARS = 4_000
MAX_LINE_CHARS = 800
MAX_MATCHES = 50


def _allowed_root() -> Path:
    configured = os.environ.get("MCP_FILE_ROOT", "").strip()
    if not configured:
        raise ValueError("MCP_FILE_ROOT must be an explicitly approved directory")
    try:
        root = Path(configured).expanduser().resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("Configured MCP_FILE_ROOT is unavailable") from exc
    if not root.is_dir():
        raise ValueError("Configured MCP_FILE_ROOT is not a directory")
    return root


def _checked_file(path: str) -> Path:
    if not isinstance(path, str) or not path.strip() or "\x00" in path:
        raise ValueError("A non-empty relative UTF-8 file path is required")
    requested = Path(path)
    if requested.is_absolute() or ".." in requested.parts:
        raise ValueError("Only paths relative to MCP_FILE_ROOT are permitted")
    root = _allowed_root()
    candidate = root
    for component in requested.parts:
        candidate = candidate / component
        # Exclude symlinks even when they currently resolve within the root.
        # A user-writable root still needs OS-level isolation against races.
        if candidate.is_symlink():
            raise ValueError("Symbolic links are not permitted")
    try:
        resolved = candidate.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ValueError("Requested file is unavailable") from exc
    if resolved == root or not resolved.is_relative_to(root):
        raise ValueError("Requested file is outside MCP_FILE_ROOT")
    if not resolved.is_file():
        raise ValueError("Requested path must be a regular file")
    return resolved


def _read_text(path: str) -> str:
    file_path = _checked_file(path)
    try:
        # Read at most one byte beyond the configured cap; stat() alone can
        # race with a concurrent writer and is not a memory bound.
        with file_path.open("rb") as source:
            payload = source.read(MAX_FILE_BYTES + 1)
    except OSError as exc:
        raise ValueError("File could not be read") from exc
    if len(payload) > MAX_FILE_BYTES:
        raise ValueError("File exceeds the maximum permitted size")
    try:
        return payload.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("File is not valid UTF-8 text") from exc


@mcp.tool
def summarize_text_file(path: str, preview_chars: int = 1200) -> dict[str, int | str]:
    """Summarize a relative UTF-8 file in MCP_FILE_ROOT, with bounded preview."""
    safe_preview = max(0, min(preview_chars, MAX_PREVIEW_CHARS))
    text = _read_text(path)
    return {
        "path": path,
        "characters": len(text),
        "lines": len(text.splitlines()),
        "preview": text[:safe_preview],
    }


@mcp.tool
def search_text_file(path: str, needle: str, max_matches: int = 20) -> dict[str, Any]:
    """Search bounded line fragments in one permitted UTF-8 file."""
    if not isinstance(needle, str) or not needle or len(needle) > 256:
        raise ValueError("needle must contain between 1 and 256 characters")
    safe_matches = max(1, min(max_matches, MAX_MATCHES))
    matches: list[dict[str, Any]] = []
    for line_number, line in enumerate(_read_text(path).splitlines(), start=1):
        if needle.casefold() in line.casefold():
            matches.append({"line_number": line_number, "line": line[:MAX_LINE_CHARS]})
            if len(matches) >= safe_matches:
                break
    return {"path": path, "needle": needle, "matches": matches}


@mcp.resource("file://{path}")
def read_file_resource(path: str) -> str:
    """Read a relative text file; apply the same root and byte limits as tools."""
    return _read_text(path)


if __name__ == "__main__":
    mcp.run()
