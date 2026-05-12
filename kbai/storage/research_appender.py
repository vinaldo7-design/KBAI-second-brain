"""Stage 3 item 2: append a dated Perplexity research section to a note.

Discipline: never rewrites existing prose. Findings live ONLY under
`## External research (Perplexity, YYYY-MM-DD)`. Idempotent per day —
calling again on the same date is a no-op and returns already_present.

This is the single-writer replacement for perplexitymcp.apply_research.
perplexitymcp keeps a wrapper that delegates here in a future step;
for now it still has its own implementation (Stage 1 invariant: zero
changes to perplexitymcp/server.py in this stage).
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from kbai.contracts import ResearchPayload, WriteReceipt
from kbai.embed.reindex_hooks import update_note_embeddings
from kbai.graph.reindex_hooks import update_note_edges
from kbai.storage.note_io import find_note_file
from kbai.storage.write_journal import record_mutation


_TOOL = "write_append_research_section"
_SECTION_HEAD_PREFIX = "## External research (Perplexity"


def _today_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _normalise_payload(payload) -> ResearchPayload | None:
    """Accept dict or ResearchPayload; return validated model or None."""
    if isinstance(payload, ResearchPayload):
        return payload
    if isinstance(payload, dict):
        # note_id is required by ResearchPayload; populate placeholder if absent
        data = dict(payload)
        data.setdefault("note_id", "")
        try:
            return ResearchPayload(**data)
        except Exception:
            return None
    return None


def _fmt_source(s) -> str:
    title = (s.title or "(untitled)") if hasattr(s, "title") else (s.get("title") or "(untitled)")
    url = (s.url or "") if hasattr(s, "url") else (s.get("url") or "")
    return f"- {title}: {url}"


def _fmt_claim(c) -> str:
    snippet = c.claim_snippet if hasattr(c, "claim_snippet") else c.get("claim_snippet", "")
    verdict = c.verdict if hasattr(c, "verdict") else c.get("verdict", "uncertain")
    confidence = None
    if hasattr(c, "model_extra") and c.model_extra:
        confidence = c.model_extra.get("confidence")
    if confidence is None and isinstance(c, dict):
        confidence = c.get("confidence")
    tail = f" (confidence: {confidence})" if confidence is not None else ""
    return f"- {snippet} — {verdict}{tail}"


def _fmt_cross_link(cl) -> str:
    vault_id = None
    hint = ""
    if hasattr(cl, "vault_note_id"):
        vault_id = cl.vault_note_id
        hint = cl.hint_text or ""
    else:
        vault_id = cl.get("vault_note_id")
        hint = cl.get("hint_text") or ""
    if vault_id:
        return f"- [[{vault_id}]]"
    return f"- {hint}"


def _fmt_question(q) -> str:
    if hasattr(q, "question"):
        return f"- {q.question}"
    return f"- {q.get('question', '')}"


def _render_section(payload: ResearchPayload, date_str: str) -> str:
    lines: list[str] = [f"## External research (Perplexity, {date_str})", ""]

    if payload.sources:
        lines.append("**Sources**")
        for s in payload.sources:
            lines.append(_fmt_source(s))
        lines.append("")

    if payload.claim_checks:
        lines.append("**Claim checks**")
        for c in payload.claim_checks:
            lines.append(_fmt_claim(c))
        lines.append("")

    if payload.cross_links:
        lines.append("**Cross-links**")
        for cl in payload.cross_links:
            lines.append(_fmt_cross_link(cl))
        lines.append("")

    if payload.open_questions:
        lines.append("**Open questions**")
        for q in payload.open_questions:
            lines.append(_fmt_question(q))
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


def _todays_section_present(text: str, date_str: str) -> bool:
    pattern = re.compile(
        rf"^##\s+External research \(Perplexity,\s*{re.escape(date_str)}\)\s*$",
        re.MULTILINE,
    )
    return bool(pattern.search(text))


def _error_receipt(message: str, note_id: str | None) -> WriteReceipt:
    return WriteReceipt(
        status="error",
        tool=_TOOL,
        note_id=note_id,
        applied=False,
        message=message,
    )


def append_research_section(
    vault_root: Path,
    note_id: str,
    payload,
    dryrun: bool = False,
) -> WriteReceipt:
    """Append today's research section to the named note. Idempotent per day.
    Returns WriteReceipt. Never raises on lookup/IO problems."""
    vault_root = Path(vault_root)

    if not isinstance(note_id, str) or not note_id:
        return _error_receipt("note_id must be a non-empty string", note_id)

    model = _normalise_payload(payload)
    if model is None:
        return _error_receipt("payload could not be parsed as a ResearchPayload", note_id)

    note_file = find_note_file(note_id, vault_root)
    if note_file is None:
        return _error_receipt(f"note '{note_id}' not found under {vault_root}", note_id)

    try:
        original = note_file.read_text(encoding="utf-8")
    except OSError as e:
        return _error_receipt(f"read failed: {e}", note_id)

    hash_before = hashlib.sha256(note_file.read_bytes()).hexdigest()
    date_str = _today_utc()
    rel_file = _rel_or_abs(note_file, vault_root)

    if _todays_section_present(original, date_str):
        return WriteReceipt(
            status="already_present",
            tool=_TOOL,
            note_id=note_id,
            applied=False,
            dryrun=dryrun,
            file=rel_file,
            hash_before=hash_before,
            hash_after=hash_before,
            message=f"section for {date_str} already present — no-op",
        )

    section = _render_section(model, date_str)
    new_content = original.rstrip() + "\n\n" + section

    if dryrun:
        return WriteReceipt(
            status="dry_run",
            tool=_TOOL,
            note_id=note_id,
            applied=False,
            dryrun=True,
            file=rel_file,
            hash_before=hash_before,
            hash_after=None,
            section_chars=len(section),
            message=f"dryrun — would append {len(section)} chars to {rel_file}",
        )

    try:
        note_file.write_text(new_content, encoding="utf-8")
    except OSError as e:
        return _error_receipt(f"write failed: {e}", note_id)

    hash_after = hashlib.sha256(note_file.read_bytes()).hexdigest()

    update_note_embeddings(note_id)
    update_note_edges(note_id)

    journal_id = record_mutation(
        vault_root=vault_root,
        tool=_TOOL,
        note_id=note_id,
        file=rel_file,
        hash_before=hash_before,
        hash_after=hash_after,
        status="applied",
        dryrun=False,
        payload_json=json.dumps(
            {
                "date": date_str,
                "section_chars": len(section),
                "n_sources": len(model.sources),
                "n_claims": len(model.claim_checks),
                "n_cross_links": len(model.cross_links),
                "n_open_questions": len(model.open_questions),
            }
        ),
    )

    now = _now_iso()
    return WriteReceipt(
        status="applied",
        tool=_TOOL,
        note_id=note_id,
        applied=True,
        dryrun=False,
        file=rel_file,
        hash_before=hash_before,
        hash_after=hash_after,
        section_chars=len(section),
        ts=now,
        applied_at=now,
        journal_id=journal_id,
    )


def _rel_or_abs(note_file: Path, vault_root: Path) -> str:
    try:
        return str(note_file.relative_to(vault_root))
    except ValueError:
        return str(note_file)
