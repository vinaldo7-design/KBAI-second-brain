"""Stage 3 item 3 (Step A): extracted from pile_a_patcher.py.

Inserts a wikilink under a typed-link section in a note body. Returns
(new_text, status) — never raises, never touches the filesystem.

Status taxonomy:
  patched          — link inserted, new_text differs from input
  already_present  — link already exists in that section, no change
  no_section       — the target section heading was not found
"""

from __future__ import annotations

import re


EDGE_HEADING: dict[str, str] = {
    "builds-on": "### Builds on",
    "builds-toward": "### Builds toward",
    "contradicts": "### Contradicts",
    "analogous-to": "### Analogous to",
    "referenced-in-maps": "### Referenced in Maps",
}


def patch_section(text: str, edge_type: str, target_stem: str) -> tuple[str, str]:
    """Insert `- [[target_stem]]` under the `### {edge_type}` heading.

    Returns (new_text, status). Status ∈ {patched, already_present, no_section}.
    Unknown edge_type also returns ("", "no_section") rather than raising,
    so bulk callers can aggregate results uniformly.
    """
    heading = EDGE_HEADING.get(edge_type)
    if heading is None:
        return text, "no_section"

    heading_re = re.compile(rf"^{re.escape(heading)}\s*$", re.MULTILINE)
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
