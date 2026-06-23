"""writeagentmcp — the only component permitted to mutate the vault.

Exposes two tools:
  write_create_note (real)
  write_apply_link_suggestions (real)

Every real tool body is ≤5 lines and delegates straight into
kbai/storage/{note_creator,link_applier,write_journal}.

Single-writer invariant: minivinnymcp must NEVER call these tools or call
write_text on vault files. All mutations land here.
"""

import os
import sys
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_VAULT_ROOT = Path(os.environ.get("VAULT_ROOT", "."))
sys.path.insert(0, str(_VAULT_ROOT))

from kbai.storage.link_applier import apply_link_suggestions  # noqa: E402
from kbai.storage.note_creator import create_note  # noqa: E402

app = FastMCP("write-agent")


@app.tool()
def write_create_note(
    folder: str,
    note_id: str,
    frontmatter: dict,
    body: str,
    dryrun: bool = False,
) -> dict:
    """Create a new vault note. Refuses to overwrite. Returns a WriteReceipt."""
    return create_note(_VAULT_ROOT, folder, note_id, frontmatter, body, dryrun).model_dump()


@app.tool()
def write_apply_link_suggestions(
    suggestions: list[dict],
    dryrun: bool = False,
) -> dict:
    """Bulk-apply link suggestions to typed-link sections.
    Returns a WriteReceipt with per-suggestion results + aggregate counts."""
    return apply_link_suggestions(_VAULT_ROOT, suggestions, dryrun).model_dump()


if __name__ == "__main__":
    app.run()
