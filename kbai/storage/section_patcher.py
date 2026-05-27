"""Stage 3 item 3 (Step A): inserts a wikilink under a typed-link section in a
note body. Returns (new_text, status) — never raises, never touches the
filesystem.

Phase 3 (2b sequel): `EDGE_HEADING` is no longer hardcoded. It is derived from
`vault_taxonomy.yaml` at module load — one source of truth for edge types on
both the parser side and the writer side. Heading matching is case-insensitive
so existing notes (sentence-case, title-case, etc.) all resolve.

Status taxonomy:
  patched          — link inserted, new_text differs from input
  already_present  — link already exists in that section, no change
  no_section       — the target section heading was not found
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import yaml


def _taxonomy_path() -> Path:
    """Find vault_taxonomy.yaml. Prefers $VAULT_ROOT, falls back to a relative
    path resolved from this module's location."""
    if env := os.environ.get("VAULT_ROOT"):
        candidate = Path(env) / "vault_taxonomy.yaml"
        if candidate.exists():
            return candidate
    fallback = Path(__file__).resolve().parent.parent.parent / "vault_taxonomy.yaml"
    if fallback.exists():
        return fallback
    raise FileNotFoundError(
        "vault_taxonomy.yaml not found (checked $VAULT_ROOT and module-relative path)"
    )


def _load_edge_headings() -> dict[str, str]:
    """Build {edge_type: '### Heading'} from vault_taxonomy.yaml.

    The yaml stores `section_heading` in lowercase (parser-side convention);
    here we display it with the first letter uppercased. Edge types without a
    section_heading (e.g. `untyped`, `mentioned`) are omitted — passing those
    to `patch_section` correctly returns "no_section".
    """
    with open(_taxonomy_path(), encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    headings: dict[str, str] = {}
    for edge_type, meta in (data.get("edge_types") or {}).items():
        sh = (meta or {}).get("section_heading")
        if not sh:
            continue
        display = sh[0].upper() + sh[1:]
        headings[edge_type] = f"### {display}"
    return headings


EDGE_HEADING: dict[str, str] = _load_edge_headings()


def patch_section(text: str, edge_type: str, target_stem: str) -> tuple[str, str]:
    """Insert `- [[target_stem]]` under the `### {edge_type}` heading.

    Returns (new_text, status). Status ∈ {patched, already_present, no_section}.
    Unknown edge_type also returns ("", "no_section") rather than raising,
    so bulk callers can aggregate results uniformly.
    """
    heading = EDGE_HEADING.get(edge_type)
    if heading is None:
        return text, "no_section"

    heading_re = re.compile(
        rf"^{re.escape(heading)}\s*$",
        re.MULTILINE | re.IGNORECASE,
    )
    m = heading_re.search(text)
    if not m:
        return text, "no_section"

    section_start = m.end()
    next_re = re.compile(r"^#{2,3}\s", re.MULTILINE)
    nm = next_re.search(text, section_start)
    section_end = nm.start() if nm else len(text)
    section_body = text[section_start:section_end]

    if f"[[{target_stem}]]" in section_body:
        return text, "already_present"

    stripped = section_body.strip()
    new_line = f"- [[{target_stem}]]"

    if stripped in ("", "-"):
        # Empty placeholder section — replace whole body
        new_body = f"\n{new_line}\n\n"
    else:
        # Append to existing list, preserve trailing blank line before next section
        new_body = section_body.rstrip() + f"\n{new_line}\n\n"

    new_text = text[:section_start] + new_body + text[section_end:]
    return new_text, "patched"
