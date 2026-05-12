"""Stage 3 transitional: write_append_research_section + write_create_note are
now real (Items 1 and 2). write_apply_link_suggestions remains a stub until
Item 3. The exhaustive real tests live in test_write_real.py (Item 6).

This file retains only the assertions that still hold against the real
implementation: server surface area and stub validation for the one tool
still in stub form."""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from writeagentmcp.server import (  # noqa: E402
    app,
    write_apply_link_suggestions,
)


def test_server_exposes_expected_tools():
    tm = getattr(app, "_tool_manager", None)
    if tm is None:
        return
    names = set(tm._tools.keys())
    assert {
        "write_create_note",
        "write_append_research_section",
        "write_apply_link_suggestions",
    } <= names


# --- write_apply_link_suggestions (still a stub until Item 3) ---

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
