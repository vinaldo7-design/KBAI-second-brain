"""Regenerate Templates/*.md from kbai/templates/*.md.

Phase 6c — single source of truth for body skeletons lives in kbai/templates/.
This script derives the Obsidian Templater files. Idempotent.

Frontmatter substitutions:
    id:           (empty)       → {{date:YYYYMMDDHHmm}}
    created:      (empty)       → {{date:YYYY-MM-DD}}
    updated:      (empty)       → {{date:YYYY-MM-DD}}
    title:        {title}       → (empty)
    summary:      {summary}     → (empty)

Body substitutions:
    {title}                     → {{title}}
    {summary}                   → {{summary}}
    - created                   → - {{date:YYYY-MM-DD}} — created
    - captured                  → - {{date:YYYY-MM-DD}} — captured

A footer HTML comment `<!-- generated ... -->` is appended to mark the file
as derived. Obsidian renders it as nothing in preview.

Run: python scripts/regenerate_obsidian_templates.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path


VAULT_ROOT = Path(__file__).resolve().parent.parent
CANONICAL_DIR = VAULT_ROOT / "kbai" / "templates"
TEMPLATER_DIR = VAULT_ROOT / "Templates"


def _transform_frontmatter(fm: str) -> str:
    fm = re.sub(r"^id:\s*$", "id: {{date:YYYYMMDDHHmm}}", fm, flags=re.MULTILINE)
    fm = re.sub(r"^created:\s*$", "created: {{date:YYYY-MM-DD}}", fm, flags=re.MULTILINE)
    fm = re.sub(r"^updated:\s*$", "updated: {{date:YYYY-MM-DD}}", fm, flags=re.MULTILINE)
    fm = re.sub(r"^title: \{title\}\s*$", "title: ", fm, flags=re.MULTILINE)
    fm = re.sub(r"^summary: \{summary\}\s*$", "summary: ", fm, flags=re.MULTILINE)
    return fm


def _transform_body(body: str) -> str:
    body = body.replace("{title}", "{{title}}")
    body = body.replace("{summary}", "{{summary}}")
    body = re.sub(
        r"^- (created|captured)$",
        r"- {{date:YYYY-MM-DD}} — \1",
        body,
        flags=re.MULTILINE,
    )
    return body


def regenerate_one(source: Path, target: Path) -> bool:
    text = source.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    if len(parts) < 3:
        raise ValueError(f"{source}: missing frontmatter delimiters")
    fm, body = parts[1], parts[2]

    new_fm = _transform_frontmatter(fm)
    new_body = _transform_body(body)
    footer = f"\n<!-- generated from kbai/templates/{source.name} — do not edit by hand -->\n"
    output = f"---\n{new_fm}---\n{new_body.rstrip()}\n{footer}"

    if target.exists() and target.read_text(encoding="utf-8") == output:
        return False
    target.write_text(output, encoding="utf-8")
    return True


def main() -> int:
    if not CANONICAL_DIR.exists():
        print(f"error: canonical dir missing: {CANONICAL_DIR}", file=sys.stderr)
        return 2
    TEMPLATER_DIR.mkdir(exist_ok=True)
    changed: list[str] = []
    unchanged: list[str] = []
    for source in sorted(CANONICAL_DIR.glob("*.md")):
        target = TEMPLATER_DIR / f"{source.stem}-note.md"
        if regenerate_one(source, target):
            changed.append(target.name)
        else:
            unchanged.append(target.name)
    if changed:
        print("regenerated:", ", ".join(changed))
    if unchanged:
        print("unchanged: ", ", ".join(unchanged))
    return 0


if __name__ == "__main__":
    sys.exit(main())
