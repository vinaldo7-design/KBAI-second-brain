"""Stage 3 item 3 (Step A): inserts a wikilink under a typed-link section in a
note body. Returns (new_text, status) — never raises, never touches the
filesystem.

Phase 3 (2b sequel): `EDGE_HEADING` is no longer hardcoded. It is derived from
`vault_taxonomy.yaml` at module load — one source of truth for edge types on
both the parser side and the writer side. Heading matching is case-insensitive
so existing notes (sentence-case, title-case, etc.) all resolve.

Capture-pipeline Task 2: `patch_section` is now create-if-missing. When the
edge_type is a *valid* headed type (has a section_heading in the taxonomy) but
its heading is ABSENT in the target note, the heading is CREATED and the
labelled link inserted under it — instead of returning "no_section". This makes
`write_apply_link_suggestions` a complete bidirectional edge-patcher: reverse
labelled edges land under the right heading in existing target notes even when
those notes predate the heading. Placement of a created heading follows
canonical taxonomy order relative to the note's existing typed-link headings;
if the note has none, the heading is appended before any trailing non-link
section (e.g. "## Status Log") else at end of body. Re-running is idempotent.

Untyped / mentioned edge types (section_heading: null) still return
"no_section" — they must never materialise a structural heading.

Status taxonomy:
  patched          — link inserted, new_text differs from input
  already_present  — link already exists in that section, no change
  no_section       — edge_type has no taxonomy heading (untyped / mentioned /
                     unknown); never returned for a valid headed type
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


def _load_edge_headings() -> tuple[dict[str, str], list[str]]:
    """Build ({edge_type: '### Heading'}, canonical_order) from vault_taxonomy.yaml.

    The yaml stores `section_heading` in lowercase (parser-side convention);
    here we display it with the first letter uppercased. Edge types without a
    section_heading (e.g. `untyped`, `mentioned`) are omitted — passing those
    to `patch_section` correctly returns "no_section".

    `canonical_order` is the list of headed edge types in the order they appear
    in the yaml — the source of truth for where a created heading is inserted
    relative to a note's existing typed-link headings.
    """
    with open(_taxonomy_path(), encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    headings: dict[str, str] = {}
    order: list[str] = []
    for edge_type, meta in (data.get("edge_types") or {}).items():
        sh = (meta or {}).get("section_heading")
        if not sh:
            continue
        display = sh[0].upper() + sh[1:]
        headings[edge_type] = f"### {display}"
        order.append(edge_type)
    return headings, order


EDGE_HEADING, EDGE_ORDER = _load_edge_headings()


def _heading_re(heading: str) -> re.Pattern[str]:
    """Case-insensitive matcher for a `### Heading` line (full-line)."""
    return re.compile(rf"^{re.escape(heading)}\s*$", re.MULTILINE | re.IGNORECASE)


def _insert_missing_heading(text: str, edge_type: str, target_stem: str) -> str:
    """Return `text` with a freshly created `### {heading}` section carrying
    `- [[target_stem]]`, placed in canonical taxonomy order.

    Placement rules (in priority order):
      1. Insert before the first EXISTING typed-link heading that comes *after*
         this edge_type in EDGE_ORDER (keeps canonical ordering among link
         headings).
      2. Else (no later sibling present) insert after the LAST existing
         typed-link heading's section — i.e. append to the run of link
         headings.
      3. Else (the note has no typed-link headings at all) insert before the
         first trailing non-link section (the earliest `## ` heading that
         follows the body prose, e.g. "## Status Log"); if there is none,
         append at end of body.
    """
    heading = EDGE_HEADING[edge_type]
    block = f"{heading}\n- [[{target_stem}]]\n\n"

    # Map each existing headed edge_type to the (start, end) span of its line.
    present: dict[str, re.Match[str]] = {}
    for et, h in EDGE_HEADING.items():
        m = _heading_re(h).search(text)
        if m:
            present[et] = m

    if present:
        my_rank = EDGE_ORDER.index(edge_type)
        # Rule 1: first existing heading whose canonical rank is greater.
        later = [
            (EDGE_ORDER.index(et), m.start())
            for et, m in present.items()
            if EDGE_ORDER.index(et) > my_rank
        ]
        if later:
            insert_at = min(later, key=lambda t: t[0])[1]
            return text[:insert_at] + block + text[insert_at:]

        # Rule 2: no later sibling — append after the last existing link
        # section. Find the section end of the last-by-rank present heading.
        last_match = max(present.values(), key=lambda m: m.start())
        section_start = last_match.end()
        nm = re.compile(r"^#{2,3}\s", re.MULTILINE).search(text, section_start)
        section_end = nm.start() if nm else len(text)
        insert_at = section_end
        prefix = text[:insert_at]
        # Guarantee a blank line separates the previous section from the new one.
        if not prefix.endswith("\n\n"):
            prefix = prefix.rstrip("\n") + "\n\n"
        return prefix + block + text[insert_at:]

    # Rule 3: note has no typed-link headings. Place the new link section just
    # before the trailing non-link section (e.g. "## Status Log") so labelled
    # links sit at the bottom of the body, after the prose. We anchor on the
    # LAST `## ` heading — in these skeletons that is the Status Log / trailing
    # log section. If there is no `## ` heading at all, append at end of body.
    h2_matches = list(re.compile(r"^##\s", re.MULTILINE).finditer(text))
    if h2_matches:
        insert_at = h2_matches[-1].start()
        prefix = text[:insert_at]
        if not prefix.endswith("\n\n"):
            prefix = prefix.rstrip("\n") + "\n\n"
        return prefix + block + text[insert_at:]

    body = text.rstrip("\n")
    sep = "\n\n" if body else ""
    return f"{body}{sep}{block}"


def patch_section(text: str, edge_type: str, target_stem: str) -> tuple[str, str]:
    """Insert `- [[target_stem]]` under the `### {edge_type}` heading.

    Returns (new_text, status). Status ∈ {patched, already_present, no_section}.

    Create-if-missing: when `edge_type` is a valid headed type whose heading is
    absent from `text`, the heading is created in canonical taxonomy order and
    the link inserted under it (status "patched"). Untyped / mentioned / unknown
    edge types (no taxonomy heading) return ("", "no_section") rather than
    raising, so bulk callers can aggregate results uniformly.
    """
    heading = EDGE_HEADING.get(edge_type)
    if heading is None:
        return text, "no_section"

    m = _heading_re(heading).search(text)
    if not m:
        # Idempotency guard: if the link already exists anywhere as a list item
        # we never duplicate it — but a missing heading means it cannot be a
        # labelled edge yet, so create the heading and insert.
        return _insert_missing_heading(text, edge_type, target_stem), "patched"

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
