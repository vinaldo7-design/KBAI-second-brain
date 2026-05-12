"""Stage 3 transitional shim: all three write tools are now real (Items 1-3).
The exhaustive real tests live in test_write_real.py (Item 6). This file
only checks that the server exposes the expected tool surface."""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from writeagentmcp.server import app  # noqa: E402


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
