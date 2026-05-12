"""writeagentmcp — the only component permitted to mutate the vault.

Stage 3 goes live incrementally:
  Item 1 — write_create_note (real)
  Item 2 — write_append_research_section (real)
  Item 3 — write_apply_link_suggestions (real)

Every real tool body is ≤5 lines and delegates straight into
kbai/storage/{note_creator,research_appender,link_applier,write_journal}.

Single-writer invariant: minivinnymcp and perplexitymcp must NEVER call
these tools or call write_text on vault files. All mutations land here.
"""

import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from mcp.server.fastmcp import FastMCP

_VAULT_ROOT = Path(os.environ.get("VAULT_ROOT", "."))
sys.path.insert(0, str(_VAULT_ROOT))

from kbai.embed.reindex_hooks import update_note_embeddings  # noqa: E402
from kbai.graph.reindex_hooks import update_note_edges  # noqa: E402
from kbai.storage.note_creator import create_note  # noqa: E402

app = FastMCP("write-agent")


def _stub_receipt(tool: str, note_id: str, **extra) -> dict:
    return {
        "status": "stub",
        "tool": tool,
        "note_id": note_id,
        "would_apply": True,
        "applied": False,
        "vault_root": str(_VAULT_ROOT),
        "ts": datetime.now(timezone.utc).isoformat(),
        "stage": 0,
        "message": "Stage 0 stub — real mutation lands in Stage 3.",
        **extra,
    }


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
def write_append_research_section(
    note_id: str,
    payload: dict,
    dryrun: bool = True,
) -> dict:
    """STAGE 0 STUB: previews appending a Perplexity research section.
    Validates input, returns a stub receipt, never writes. Real impl lands in Item 2."""
    if not isinstance(note_id, str) or not note_id:
        return {"error": "note_id must be a non-empty string"}
    if not isinstance(payload, dict):
        return {"error": "payload must be a dict"}
    expected_keys = {"sources", "claim_checks", "cross_links", "open_questions"}
    reindex_hint_embed = update_note_embeddings(note_id)
    reindex_hint_graph = update_note_edges(note_id)
    return _stub_receipt(
        tool="write_append_research_section",
        note_id=note_id,
        target_section="## External research (Perplexity, YYYY-MM-DD)",
        payload_keys=sorted(payload.keys()),
        recognised_keys=sorted(expected_keys & set(payload.keys())),
        dryrun=dryrun,
        reindex_hint_embed=reindex_hint_embed,
        reindex_hint_graph=reindex_hint_graph,
    )


@app.tool()
def write_apply_link_suggestions(
    suggestions: list[dict],
    dryrun: bool = True,
) -> dict:
    """STAGE 0 STUB: previews application of link suggestions from
    analytics_connect_suggest. Real impl lands in Item 3."""
    if not isinstance(suggestions, list):
        return {"error": "suggestions must be a list"}
    valid: list[dict] = []
    invalid: list[dict] = []
    for s in suggestions:
        if (
            isinstance(s, dict)
            and isinstance(s.get("source"), str)
            and isinstance(s.get("target"), str)
            and isinstance(s.get("edge_type") or s.get("suggested_type"), str)
        ):
            valid.append(s)
        else:
            invalid.append(s)
    return {
        "status": "stub",
        "tool": "write_apply_link_suggestions",
        "would_apply_count": len(valid),
        "rejected_count": len(invalid),
        "applied": False,
        "dryrun": dryrun,
        "stage": 0,
        "message": "Stage 0 stub — real mutation lands in Stage 3.",
    }


if __name__ == "__main__":
    app.run()
