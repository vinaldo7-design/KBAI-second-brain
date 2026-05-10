"""Stage 9 — recent_notes MCP tool tests.

L1 — basic return shape + ordering
L2 — since_ts filter
L3 — topic filter
L4 — limit cap
L5 — skip-dirs exclusion
"""

import os
import sys
import time
from pathlib import Path

import pytest

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))


# ── fixture: synthetic vault in tmp_path ──────────────────────────────────────

@pytest.fixture()
def fake_vault(tmp_path, monkeypatch):
    """Create a minimal vault tree and patch server globals."""
    import minivinnymcp.server as srv

    # Build note files at different mtimes
    notes = [
        ("01-Concepts/alpha-concept.md", 1_000_100),
        ("01-Concepts/beta-concept.md", 1_000_200),
        ("02-Learning/gamma-note.md",   1_000_300),
        ("02-Learning/delta-note.md",   1_000_400),
    ]
    for rel, mtime in notes:
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"# {p.stem}\n\nContent.")
        os.utime(p, (mtime, mtime))

    # System dirs that should be skipped
    skip = tmp_path / ".obsidian" / "skip-me.md"
    skip.parent.mkdir(parents=True, exist_ok=True)
    skip.write_text("hidden")
    os.utime(skip, (9_999_999, 9_999_999))  # newest possible — must not appear

    trash = tmp_path / ".trash" / "gone.md"
    trash.parent.mkdir(parents=True, exist_ok=True)
    trash.write_text("trashed")
    os.utime(trash, (9_999_999, 9_999_999))

    monkeypatch.setattr(srv, "_vault_root", tmp_path)
    return tmp_path


# ── L1: shape + ordering ──────────────────────────────────────────────────────

def test_returns_list_of_dicts(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=10)
    assert isinstance(result, list)
    assert all(isinstance(r, dict) for r in result)


def test_required_keys_present(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=1)
    assert result
    r = result[0]
    for key in ("note_id", "title", "modified_ts", "modified_iso", "summary"):
        assert key in r, f"missing key: {key}"


def test_ordered_newest_first(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=10)
    mtimes = [r["modified_ts"] for r in result]
    assert mtimes == sorted(mtimes, reverse=True)


def test_newest_is_delta(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=1)
    assert result[0]["note_id"] == "delta-note"


def test_modified_iso_format(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=1)
    iso = result[0]["modified_iso"]
    # Basic ISO check: YYYY-MM-DDTHH:MM:SSZ
    assert len(iso) == 20
    assert iso[10] == "T"
    assert iso[-1] == "Z"


# ── L2: since_ts filter ───────────────────────────────────────────────────────

def test_since_ts_excludes_old_notes(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=10, since_ts=1_000_250)
    note_ids = [r["note_id"] for r in result]
    assert "gamma-note" in note_ids
    assert "delta-note" in note_ids
    assert "alpha-concept" not in note_ids
    assert "beta-concept" not in note_ids


def test_since_ts_inclusive_boundary(fake_vault):
    from minivinnymcp.server import recent_notes
    # since_ts=1_000_300 should include gamma-note (mtime==1_000_300)
    result = recent_notes(limit=10, since_ts=1_000_300)
    note_ids = [r["note_id"] for r in result]
    assert "gamma-note" in note_ids


def test_since_ts_none_returns_all(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=100, since_ts=None)
    assert len(result) == 4


# ── L3: topic filter ──────────────────────────────────────────────────────────

def test_topic_filter_matches_substring(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=10, topic="concept")
    note_ids = [r["note_id"] for r in result]
    assert set(note_ids) == {"alpha-concept", "beta-concept"}


def test_topic_filter_case_insensitive(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=10, topic="CONCEPT")
    assert len(result) == 2


def test_topic_filter_no_match_returns_empty(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=10, topic="zzz-nonexistent")
    assert result == []


# ── L4: limit ─────────────────────────────────────────────────────────────────

def test_limit_caps_results(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=2)
    assert len(result) == 2


def test_limit_larger_than_available(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=100)
    assert len(result) == 4


# ── L5: skip dirs ─────────────────────────────────────────────────────────────

def test_obsidian_dir_excluded(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=100)
    note_ids = [r["note_id"] for r in result]
    assert "skip-me" not in note_ids


def test_trash_dir_excluded(fake_vault):
    from minivinnymcp.server import recent_notes
    result = recent_notes(limit=100)
    note_ids = [r["note_id"] for r in result]
    assert "gone" not in note_ids


# ── L6: tool registered in MCP ───────────────────────────────────────────────

def test_recent_notes_registered_in_mcp():
    from minivinnymcp.server import app
    tool_names = [t.name for t in app._tool_manager.list_tools()]
    assert "recent_notes" in tool_names
