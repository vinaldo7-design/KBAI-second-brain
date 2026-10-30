"""Apply a reviewed list of links through the journalled writer.

    python -m kbai.links links.json [--dry-run]

Each entry is {"source", "target", "type", "why"}. The whole list is checked before
anything is written, reasons are stored on the links, and two-way types get their
mirror line. Afterwards the vault audit runs.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

from kbai.storage.link_applier import apply_link_suggestions
from kbai.storage.note_io import find_note_file
from kbai.storage.section_patcher import EDGE_HEADING

MIRROR = {
    "builds-on": "builds-toward",
    "builds-toward": "builds-on",
    "contradicts": "contradicts",
    "analogous-to": "analogous-to",
}
_SAME_RELATION = {"builds-toward": "builds-on"}
_NOT_A_CLAIM = {"mentioned", "referenced-in", "untyped"}
_AUDIT = Path(__file__).resolve().parent.parent / "scripts" / "vault_audit.py"


@dataclass
class Report:
    planned: int = 0
    applied: int = 0
    already_present: int = 0
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _check(entries: list[dict], vault_root: Path) -> list[str]:
    problems = []
    for i, entry in enumerate(entries):
        source, target, kind = entry.get("source"), entry.get("target"), entry.get("type")
        label = f"entry {i} ({source} -> {target})"
        if not (source and target and kind):
            problems.append(f"{label}: missing source, target or type")
            continue
        if not entry.get("why"):
            problems.append(f"{label}: missing why")
        if source == target:
            problems.append(f"{label}: links a note to itself")
        if kind not in EDGE_HEADING or kind == "referenced-in":
            problems.append(f"{label}: unknown edge type {kind}")
        for note_id in (source, target):
            if find_note_file(note_id, vault_root) is None:
                problems.append(f"{label}: no note called {note_id}")
    return problems


def _with_mirrors(entries: list[dict]) -> list[dict]:
    lines = []
    for entry in entries:
        lines.append({"source_id": entry["source"], "target_id": entry["target"],
                      "edge_type": entry["type"], "why": entry["why"]})
        if entry["type"] in MIRROR:
            lines.append({"source_id": entry["target"], "target_id": entry["source"],
                          "edge_type": MIRROR[entry["type"]], "why": entry["why"]})
    return lines


def _double_typed(entries: list[dict], vault_root: Path) -> list[str]:
    graph_path = vault_root / "06-Maps" / "vault-graph.json"
    if not graph_path.exists():
        return []
    existing: dict[frozenset, set[str]] = {}
    for edge in json.loads(graph_path.read_text(encoding="utf-8"))["edges"]:
        if edge["type"] not in _NOT_A_CLAIM:
            kind = _SAME_RELATION.get(edge["type"], edge["type"])
            existing.setdefault(frozenset((edge["source"], edge["target"])), set()).add(kind)
    warnings = []
    for entry in entries:
        kind = _SAME_RELATION.get(entry["type"], entry["type"])
        others = existing.get(frozenset((entry["source"], entry["target"])), set()) - {kind}
        if others:
            warnings.append(
                f"{entry['source']} and {entry['target']} are already linked as {', '.join(sorted(others))}"
            )
    return warnings


def run_audit(vault_root: Path) -> str | None:
    """Return the audit's failure output, or None if it passes."""
    env = {**os.environ, "PYTHONPATH": str(_AUDIT.parent.parent)}
    result = subprocess.run(
        [sys.executable, str(_AUDIT)], cwd=vault_root, env=env, capture_output=True, text=True
    )
    return None if result.returncode == 0 else (result.stdout + result.stderr)[-1500:]


def apply_links(entries: list[dict], vault_root: Path, dry_run: bool = False) -> Report:
    vault_root = Path(vault_root)
    problems = _check(entries, vault_root)
    if problems:
        return Report(problems=problems)

    lines = _with_mirrors(entries)
    report = Report(planned=len(lines), warnings=_double_typed(entries, vault_root))
    if dry_run:
        return report

    receipt = apply_link_suggestions(vault_root, lines)
    report.applied = receipt.applied_count or 0
    report.already_present = receipt.already_present or 0
    if receipt.message:
        report.problems.append(receipt.message)
    report.problems.extend(
        f"{row.get('source_id')} -> {row.get('target_id')}: {row['status']}"
        for row in receipt.results or []
        if row.get("status") not in ("patched", "already_present")
    )
    audit_failure = run_audit(vault_root)
    if audit_failure:
        report.problems.append(f"vault audit failed:\n{audit_failure}")
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply a reviewed list of links.")
    parser.add_argument("file", type=Path)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    vault_root = Path(os.environ.get("VAULT_ROOT") or Path.cwd())
    entries = json.loads(args.file.read_text(encoding="utf-8"))

    if not args.dry_run:
        from kbai import notes_history
        notes_history.snapshot(vault_root, f"before links from {args.file.name}")
    report = apply_links(entries, vault_root, dry_run=args.dry_run)
    if not args.dry_run and report.applied:
        notes_history.snapshot(vault_root, f"links from {args.file.name}")

    verb = "would write" if args.dry_run else "wrote"
    count = report.planned if args.dry_run else report.applied
    print(f"{verb} {count} of {report.planned} lines; {report.already_present} already present")
    for warning in report.warnings:
        print(f"warning: {warning}")
    for problem in report.problems:
        print(f"problem: {problem}", file=sys.stderr)
    return 1 if report.problems else 0


if __name__ == "__main__":
    sys.exit(main())
