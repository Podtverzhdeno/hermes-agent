"""Exercise the bundled FastMCP file template without installing FastMCP."""
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

TEMPLATE = Path(__file__).resolve().parents[2] / "optional-skills/mcp/fastmcp/templates/file_processor.py"

def _load(monkeypatch):
    class FakeMCP:
        def __init__(self, name):
            self.name = name
        @staticmethod
        def tool(fn):
            return fn
        @staticmethod
        def resource(uri):
            return lambda fn: fn
    monkeypatch.setitem(sys.modules, "fastmcp", SimpleNamespace(FastMCP=FakeMCP))
    return runpy.run_path(str(TEMPLATE))

def test_requires_explicit_root(monkeypatch):
    monkeypatch.delenv("MCP_FILE_ROOT", raising=False)
    m = _load(monkeypatch)
    with pytest.raises(ValueError, match="MCP_FILE_ROOT"):
        m["_read_text"]("any.txt")

def test_allowed_relative_read_with_bounded_outputs(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    (root / "x.txt").write_text("first\n" + "needle" * 200 + "\nlast", encoding="utf-8")
    monkeypatch.setenv("MCP_FILE_ROOT", str(root))
    m = _load(monkeypatch)
    summary = m["summarize_text_file"]("x.txt", preview_chars=100000)
    assert summary["lines"] == 3 and summary["path"] == "x.txt"
    assert len(summary["preview"]) <= 4000
    hits = m["search_text_file"]("x.txt", "NEEDLE", max_matches=500)
    assert len(hits["matches"]) == 1
    assert hits["matches"][0]["line_number"] == 2
    assert len(hits["matches"][0]["line"]) <= 800
    assert m["read_file_resource"]("x.txt").endswith("last")

@pytest.mark.parametrize("bad", ["../secret.txt", "../../secret.txt", "/etc/passwd", ""])
def test_denies_traversal_and_absolute_paths(tmp_path, monkeypatch, bad):
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("private", encoding="utf-8")
    monkeypatch.setenv("MCP_FILE_ROOT", str(root))
    m = _load(monkeypatch)
    with pytest.raises(ValueError):
        m["_read_text"](bad)

def test_symlink_escape_denied(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    outside = tmp_path / "private.txt"
    outside.write_text("secret", encoding="utf-8")
    try:
        (root / "alias.txt").symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("no symlink support")
    monkeypatch.setenv("MCP_FILE_ROOT", str(root))
    m = _load(monkeypatch)
    with pytest.raises(ValueError, match="Symbolic links"):
        m["_read_text"]("alias.txt")

def test_file_size_utf8_and_needle_limits(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setenv("MCP_FILE_ROOT", str(root))
    m = _load(monkeypatch)
    (root / "huge.txt").write_bytes(b"x" * (m["MAX_FILE_BYTES"] + 1))
    with pytest.raises(ValueError, match="maximum"):
        m["read_file_resource"]("huge.txt")
    (root / "bad.txt").write_bytes(b"\xff")
    with pytest.raises(ValueError, match="UTF-8"):
        m["_read_text"]("bad.txt")
    with pytest.raises(ValueError, match="needle"):
        m["search_text_file"]("bad.txt", "x" * 300)

def test_max_matches_enforced(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    (root / "many.txt").write_text("hit\n" * 100, encoding="utf-8")
    monkeypatch.setenv("MCP_FILE_ROOT", str(root))
    m = _load(monkeypatch)
    assert len(m["search_text_file"]("many.txt", "hit", max_matches=1000)["matches"]) == 50
