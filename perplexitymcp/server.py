"""perplexity-mcp — Perplexity Deep Research as an annotator for the vault.

Two tools:
  research_note   — call Perplexity, return structured findings (no file writes)
  apply_research  — append findings to the note as a clearly-marked section

Discipline: never silently rewrites existing prose. All Perplexity-derived
content lives under "## External research (Perplexity, YYYY-MM-DD)".
"""

import json
import os
import re
import sqlite3
import time
from datetime import datetime, timezone
from hashlib import md5
from pathlib import Path
from typing import Any

import requests
from mcp.server.fastmcp import FastMCP

_VAULT_ROOT = Path(os.environ["VAULT_ROOT"])
_GRAPH_PATH = _VAULT_ROOT / "06-Maps" / "vault-graph.json"
_LOG_DB = _VAULT_ROOT / "06-Maps" / "perplexity-research.db"

_API_URL = "https://api.perplexity.ai/chat/completions"
_MODEL = os.environ.get("PERPLEXITY_MODEL", "sonar-deep-research")
_TIMEOUT = int(os.environ.get("PERPLEXITY_TIMEOUT", "300"))

_RESEARCH_SECTION_HEADING = "## External research (Perplexity"

_JSON_SCHEMA_INSTRUCTION = """Return your findings as STRICT JSON in exactly this shape:

{
  "sources": [
    { "title": string, "url": string, "summary": string, "published": string|null }
  ],
  "claim_checks": [
    {
      "claim_snippet": string,
      "verdict": "supports"|"contradicts"|"mixed"|"uncertain",
      "evidence": [ { "url": string, "note": string } ]
    }
  ],
  "cross_links": [
    { "hint_text": string, "reason": string }
  ],
  "open_questions": [
    { "question": string, "reason": string }
  ],
  "raw_summary": string
}

Do not include any extra keys or commentary. The top-level value MUST be an object with exactly these fields."""


# --- Note resolution ------------------------------------------------------

def _find_note_file(note_id: str) -> Path | None:
    """Resolve note_id to filesystem path. Accepts bare id, relative path, or absolute path."""
    if "/" in note_id or note_id.endswith(".md"):
        p = (_VAULT_ROOT / note_id) if not Path(note_id).is_absolute() else Path(note_id)
        if p.exists():
            return p
    for p in _VAULT_ROOT.rglob(f"{note_id}.md"):
        return p
    return None


def _load_graph() -> dict | None:
    if not _GRAPH_PATH.exists():
        return None
    with open(_GRAPH_PATH, encoding="utf-8") as f:
        return json.load(f)


def _normalize(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _match_vault_note(hint_text: str, graph: dict | None) -> str | None:
    """Fuzzy match a hint to an existing vault note by title or normalised id."""
    if not graph:
        return None
    target = _normalize(hint_text)
    if not target:
        return None
    nodes = graph.get("nodes", [])
    for n in nodes:
        if _normalize(n.get("id", "")) == target:
            return n["id"]
    for n in nodes:
        title = n.get("title") or ""
        if _normalize(title) == target:
            return n["id"]
    for n in nodes:
        title_norm = _normalize(n.get("title") or "")
        if title_norm and (target in title_norm or title_norm in target):
            return n["id"]
    return None


# --- Perplexity call ------------------------------------------------------

def _call_perplexity(note_content: str) -> dict:
    """Call Perplexity Deep Research, return parsed JSON payload.
    Raises RuntimeError on any failure (network, status, JSON parse)."""
    api_key = os.environ.get("PERPLEXITY_API_KEY")
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY not set in environment.")

    system_prompt = (
        "You are a research agent helping update a personal knowledge note. "
        "The note content will be provided by the user.\n\n"
        "1. Find recent, high-quality sources (papers, articles, docs) directly relevant to the note.\n"
        "2. Check whether the core claims still hold according to current literature.\n"
        "3. Suggest cross-references or related concepts that should be linked.\n"
        "4. Surface open questions the note doesn't address.\n\n"
        + _JSON_SCHEMA_INSTRUCTION
    )

    payload = {
        "model": _MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Note content:\n\n{note_content}"},
        ],
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    try:
        resp = requests.post(_API_URL, json=payload, headers=headers, timeout=_TIMEOUT)
    except requests.RequestException as e:
        raise RuntimeError(f"Perplexity request failed: {e}") from e

    if resp.status_code != 200:
        raise RuntimeError(f"Perplexity returned {resp.status_code}: {resp.text[:500]}")

    try:
        data = resp.json()
        content = data["choices"][0]["message"]["content"]
    except (KeyError, ValueError) as e:
        raise RuntimeError(f"Unexpected Perplexity response shape: {e}") from e

    return _extract_json(content)


def _extract_json(content: str) -> dict:
    """Parse JSON from Perplexity output. Tolerates ```json fences and surrounding prose."""
    fence_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", content, re.DOTALL)
    if fence_match:
        candidate = fence_match.group(1)
    else:
        first = content.find("{")
        last = content.rfind("}")
        if first == -1 or last == -1 or last <= first:
            raise RuntimeError("No JSON object found in Perplexity response.")
        candidate = content[first : last + 1]

    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"Failed to parse Perplexity JSON: {e}") from e

    for key in ("sources", "claim_checks", "cross_links", "open_questions"):
        parsed.setdefault(key, [])
    parsed.setdefault("raw_summary", "")
    return parsed


# --- Logging sidecar ------------------------------------------------------

def _log_research(note_id: str, researched_at: str, content_hash: str) -> None:
    """Track when each note was last refreshed. Best-effort, never raises."""
    try:
        db = sqlite3.connect(_LOG_DB)
        db.execute(
            """CREATE TABLE IF NOT EXISTS research_log (
                note_id       TEXT,
                researched_at TEXT,
                content_hash  TEXT,
                model         TEXT
            )"""
        )
        db.execute(
            "INSERT INTO research_log VALUES (?,?,?,?)",
            (note_id, researched_at, content_hash, _MODEL),
        )
        db.commit()
        db.close()
    except Exception:
        pass


# --- Section formatting ---------------------------------------------------

def _format_research_section(payload: dict, include_raw_summary: bool) -> str:
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    lines = [f"{_RESEARCH_SECTION_HEADING}, {today})", ""]

    sources = payload.get("sources") or []
    if sources:
        lines.append("### Sources")
        for s in sources:
            title = s.get("title") or "(untitled)"
            url = s.get("url") or ""
            summary = s.get("summary") or ""
            published = s.get("published")
            pub_str = f" (published: {published})" if published else ""
            lines.append(f"- [{title}]({url}) — {summary}{pub_str}")
        lines.append("")

    claims = payload.get("claim_checks") or []
    if claims:
        lines.append("### Claim checks")
        for c in claims:
            snippet = c.get("claim_snippet") or ""
            verdict = c.get("verdict") or "uncertain"
            lines.append(f'- "{snippet}" — verdict: **{verdict}**')
            for ev in c.get("evidence") or []:
                lines.append(f"  - [{ev.get('note', 'evidence')}]({ev.get('url', '')})")
        lines.append("")

    cross = payload.get("cross_links") or []
    if cross:
        lines.append("### Cross-links")
        for cl in cross:
            vault_id = cl.get("vault_note_id")
            hint = cl.get("hint_text") or ""
            reason = cl.get("reason") or ""
            link = f"[[{vault_id}]]" if vault_id else f"_{hint}_ (no vault match)"
            lines.append(f"- {link} — {reason}")
        lines.append("")

    questions = payload.get("open_questions") or []
    if questions:
        lines.append("### Open questions")
        for q in questions:
            lines.append(f"- {q.get('question', '')} — {q.get('reason', '')}")
        lines.append("")

    if include_raw_summary and (payload.get("raw_summary") or "").strip():
        lines.append("> Raw external summary:")
        lines.append("> ```text")
        for line in payload["raw_summary"].splitlines():
            lines.append(f"> {line}")
        lines.append("> ```")
        lines.append("")

    return "\n".join(lines).rstrip() + "\n"


# --- MCP server -----------------------------------------------------------

app = FastMCP("perplexity-research")


@app.tool()
def research_note(note_id: str, mode: str = "single", cluster_hops: int = 1) -> dict:
    """Call Perplexity Deep Research on a vault note. Returns structured findings
    with sources, claim_checks, cross_links, open_questions. Does NOT modify
    the note — use apply_research to patch findings in. mode='cluster' is
    reserved for future expansion; currently behaves like 'single'."""
    note_file = _find_note_file(note_id)
    if not note_file:
        return {"error": f"Note '{note_id}' not found under {_VAULT_ROOT}"}

    note_content = note_file.read_text(encoding="utf-8")

    try:
        payload = _call_perplexity(note_content)
    except RuntimeError as e:
        return {"error": str(e)}

    graph = _load_graph()
    for cl in payload.get("cross_links") or []:
        hint = cl.get("hint_text") or ""
        match = _match_vault_note(hint, graph)
        if match:
            cl["vault_note_id"] = match

    researched_at = datetime.now(timezone.utc).isoformat()
    content_hash = md5(note_content.encode("utf-8")).hexdigest()[:12]
    _log_research(note_id, researched_at, content_hash)

    return {
        "note_id": note_id,
        "researched_at": researched_at,
        "model": _MODEL,
        "sources": payload.get("sources") or [],
        "claim_checks": payload.get("claim_checks") or [],
        "cross_links": payload.get("cross_links") or [],
        "open_questions": payload.get("open_questions") or [],
        "raw_summary": payload.get("raw_summary") or "",
    }


@app.tool()
def apply_research(
    note_id: str,
    sources: list[dict] | None = None,
    claim_checks: list[dict] | None = None,
    cross_links: list[dict] | None = None,
    open_questions: list[dict] | None = None,
    raw_summary: str = "",
    include_raw_summary: bool = True,
    researched_at: str | None = None,
) -> dict:
    """Append findings from research_note to the note as a clearly-marked section.
    Never rewrites existing prose. If a prior 'External research' section exists,
    a new dated section is appended below it (not merged)."""
    note_file = _find_note_file(note_id)
    if not note_file:
        return {"error": f"Note '{note_id}' not found under {_VAULT_ROOT}"}

    payload = {
        "sources": sources or [],
        "claim_checks": claim_checks or [],
        "cross_links": cross_links or [],
        "open_questions": open_questions or [],
        "raw_summary": raw_summary,
    }

    section = _format_research_section(payload, include_raw_summary=include_raw_summary)

    original = note_file.read_text(encoding="utf-8")
    separator = "\n\n---\n\n" if not original.endswith("\n") else "\n---\n\n"
    new_content = original.rstrip() + separator + section

    note_file.write_text(new_content, encoding="utf-8")

    return {
        "note_id": note_id,
        "applied_at": datetime.now(timezone.utc).isoformat(),
        "researched_at": researched_at,
        "section_chars": len(section),
        "file": str(note_file.relative_to(_VAULT_ROOT)),
        "status": "appended",
    }


if __name__ == "__main__":
    app.run()
