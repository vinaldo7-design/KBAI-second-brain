"""Stage 0 item 5: write-agent stubs validate input, return well-formed
stub receipts, and never mutate the real vault."""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from writeagentmcp.server import (
    app,
    write_append_research_section,
    write_apply_link_suggestions,
)


def test_server_exposes_expected_tools():
    tm = getattr(app, "_tool_manager", None)
    if tm is None:
        return
    names = set(tm._tools.keys())
    assert {"write_append_research_section", "write_apply_link_suggestions"} <= names


# --- write_append_research_section ---

def test_append_research_validates_note_id():
    out = write_append_research_section("", {})
    assert "error" in out


def test_append_research_validates_payload():
    out = write_append_research_section("some-note", "not a dict")  # type: ignore[arg-type]
    assert "error" in out


def test_append_research_returns_stub_receipt():
    payload = {"sources": [{"title": "x"}], "claim_checks": [], "cross_links": [], "open_questions": []}
    out = write_append_research_section("some-note", payload)
    assert out["status"] == "stub"
    assert out["applied"] is False
    assert out["would_apply"] is True
    assert out["tool"] == "write_append_research_section"
    assert "sources" in out["recognised_keys"]


def test_append_research_does_not_touch_filesystem(tmp_path):
    """Confirms stub does not write the named note even if it existed."""
    fake_note = tmp_path / "fake.md"
    fake_note.write_text("original content", encoding="utf-8")
    write_append_research_section(str(fake_note), {"sources": []})
    assert fake_note.read_text(encoding="utf-8") == "original content"


# --- write_apply_link_suggestions ---

def test_apply_links_validates_input_type():
    out = write_apply_link_suggestions("not a list")  # type: ignore[arg-type]
    assert "error" in out


def test_apply_links_counts_valid_and_invalid():
    suggestions = [
        {"source": "a", "target": "b", "edge_type": "builds-on"},
        {"source": "a", "target": "b", "suggested_type": "analogous-to"},
        {"target": "missing-source"},
        "not a dict",
    ]
    out = write_apply_link_suggestions(suggestions)
    assert out["status"] == "stub"
    assert out["applied"] is False
    assert out["would_apply_count"] == 2
    assert out["rejected_count"] == 2
