"""Task 4: frontmatter-SSOT conformance / idempotency / write-path guard.

Three guarantees, proven against the live corpus and the write path:

  TEST 1 — corpus conformance (drift detector): every content note's
           frontmatter validates against kbai.schema. Fails loudly with the
           offending path+error if any future note drifts.
  TEST 2 — migration idempotency: re-running the Task 3 migration
           (normalize_frontmatter) on the already-migrated corpus is a no-op.
  TEST 3 — write-path guard: kbai.storage.note_creator.create_note refuses to
           persist schema-invalid frontmatter — status=="error", applied is
           False, and NO file is written.

Tests 1 and 2 guard on the vault being present: a bare checkout (no .md notes
in the content folders) skips rather than failing, so the suite still runs.
Test 3 is hermetic (tmp_path only) and never touches the real vault.
"""

import os
import sys
from pathlib import Path

import pytest
import yaml

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.schema import validate_frontmatter
from kbai.storage.frontmatter_migrate import normalize_frontmatter
from kbai.storage.note_creator import create_note


# --- corpus layout ----------------------------------------------------------

VAULT_ROOT = _vault_root

# Content note folders (CLAUDE-static.md canonical top-level layout).
CONTENT_FOLDERS: tuple[str, ...] = (
    "00-Captures", "01-Ideas", "02-Learning", "03-Projects",
    "04-Substack", "05-Personal", "06-Maps",
)

# Non-note files to skip: housekeeping/derived files that live in the content
# folders but are not notes (no canonical frontmatter contract).
SKIP_STEMS: frozenset[str] = frozenset({"README", "readme", "connect-suggestions"})

# Known non-conformant notes excluded from the conformance assertion by user
# decision. Kept as a safety net even though one of them (cycle of suffering)
# also has no `---` block and is skipped as a non-note before this set applies.
DEFERRED: frozenset[str] = frozenset({
    "02-Learning/session-close-2026-05-01-phase2-shipped.md",
    "00-Captures/cycle of suffering.md",
})


def _parse_frontmatter(text: str) -> dict | None:
    """Return the YAML frontmatter dict between the first two `---` fences, or
    None when the file has no parseable frontmatter block (→ treat as non-note).
    """
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return None
    # split into ["", <yaml>, <rest>] on the first two fences.
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1])
    except yaml.YAMLError:
        return None
    return fm if isinstance(fm, dict) else None


def _iter_content_notes():
    """Yield (rel_path, frontmatter_dict) for every content note, skipping
    non-notes (SKIP_STEMS stems and files with no `---` frontmatter block).

    rel_path is POSIX-style relative to the vault root, e.g.
    "01-Ideas/some-note.md" — matching the DEFERRED entries.
    """
    for folder in CONTENT_FOLDERS:
        folder_path = VAULT_ROOT / folder
        if not folder_path.is_dir():
            continue
        for path in sorted(folder_path.rglob("*.md")):
            if path.stem in SKIP_STEMS:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            fm = _parse_frontmatter(text)
            if fm is None:  # no frontmatter block → not a note
                continue
            rel = path.relative_to(VAULT_ROOT).as_posix()
            yield rel, fm


def _require_corpus() -> list[tuple[str, dict]]:
    """Collect all content notes, or skip the test on a bare checkout."""
    notes = list(_iter_content_notes())
    if not notes:
        pytest.skip(
            "no content notes found under "
            f"{CONTENT_FOLDERS} in {VAULT_ROOT} — bare checkout; "
            "corpus tests require the populated vault"
        )
    return notes


# --- TEST 1: corpus conformance (drift detector) ----------------------------

def test_corpus_frontmatter_is_conformant():
    """Every content note (excluding DEFERRED) must validate against the
    schema. Collect ALL failures so drift surfaces in one report rather than
    one-at-a-time, and never loosen the assertion to hide a real failure."""
    notes = _require_corpus()

    failures: list[str] = []
    checked = 0
    for rel, fm in notes:
        if rel in DEFERRED:
            continue
        checked += 1
        error = validate_frontmatter(fm)
        if error is not None:
            failures.append(f"  {rel}\n      -> {error}")

    # Guard against a vacuous pass: if everything got filtered into DEFERRED or
    # skipped, there is nothing to assert and the test would be meaningless.
    assert checked > 0, (
        "no non-deferred content notes were checked — corpus guard is vacuous"
    )

    assert not failures, (
        f"{len(failures)} content note(s) have non-conformant frontmatter "
        f"(not in DEFERRED):\n" + "\n".join(failures)
    )


# --- TEST 2: migration idempotency ------------------------------------------

def test_migration_is_idempotent_on_migrated_corpus():
    """Re-running the Task 3 migration over the already-migrated corpus must be
    a no-op: normalize_frontmatter returns changes == [] for every conformant
    note (skipping non-notes + DEFERRED)."""
    notes = _require_corpus()

    failures: list[str] = []
    checked = 0
    for rel, fm in notes:
        if rel in DEFERRED:
            continue
        # Only assert idempotency on notes that are actually conformant; a
        # non-conformant note legitimately produces changes and is TEST 1's job.
        if validate_frontmatter(fm) is not None:
            continue
        checked += 1
        _new_fm, changes = normalize_frontmatter(fm)
        if changes:
            failures.append(f"  {rel}\n      -> {changes}")

    assert checked > 0, (
        "no conformant content notes were checked — idempotency guard is vacuous"
    )

    assert not failures, (
        f"{len(failures)} conformant note(s) were still mutated by "
        f"normalize_frontmatter (migration not idempotent):\n"
        + "\n".join(failures)
    )


# --- TEST 3: write-path guard (hermetic; tmp_path only) ----------------------

def _base_frontmatter() -> dict:
    """A minimally valid frontmatter dict. `id`/`created`/`updated` are added by
    create_note, so they are intentionally omitted here — we pass only
    type/status/summary/tags/title (per the brief)."""
    return {
        "type": "concept",
        "status": "seedling",
        "summary": "A valid one-line summary.",
        "tags": ["topic/testing"],
        "title": "Some Test Note",
    }


def _make_tmp_vault(tmp_path: Path) -> Path:
    """A throwaway vault dir with the 06-Maps content subdir."""
    vault = tmp_path / "vault"
    (vault / "06-Maps").mkdir(parents=True)
    return vault


def test_base_frontmatter_is_actually_valid(tmp_path):
    """Sanity gate for TEST 3: the uncorrupted base fm must produce a real
    write. Otherwise the invalid-input cases below could pass for the wrong
    reason (failing on the base, not on the corruption)."""
    vault = _make_tmp_vault(tmp_path)
    note_id = "valid-base-note"
    receipt = create_note(vault, "06-Maps", note_id, _base_frontmatter(), "body")
    assert receipt.status == "applied"
    assert receipt.applied is True
    assert (vault / "06-Maps" / f"{note_id}.md").exists()


def test_write_path_rejects_invalid_frontmatter(tmp_path):
    """No write path may persist schema-invalid frontmatter. For each corruption
    (one bad thing at a time on an otherwise-valid base), create_note must
    return status=="error", applied is False, and write NO file."""

    # Each case: note_id -> a mutation applied to a fresh valid base fm.
    cases: dict[str, callable] = {
        # (a) missing summary (a required field)
        "missing-summary": lambda fm: fm.pop("summary"),
        # (b) an unknown frontmatter key
        "unknown-key": lambda fm: fm.__setitem__("medium", "lecture"),
        # (c) off-enum status
        "off-enum-status": lambda fm: fm.__setitem__("status", "blooming"),
        # (d) origin on a concept note (origin is not allowed on type concept)
        "origin-on-concept": lambda fm: fm.__setitem__("origin", "lecture"),
    }

    for note_id, mutate in cases.items():
        # Fresh vault per case so a stale file from another case can't mask a
        # spurious write.
        vault = _make_tmp_vault(tmp_path / note_id)
        fm = _base_frontmatter()
        mutate(fm)

        receipt = create_note(vault, "06-Maps", note_id, fm, "body")

        target = vault / "06-Maps" / f"{note_id}.md"
        assert receipt.status == "error", (
            f"[{note_id}] expected status=='error', got {receipt.status!r} "
            f"(message={receipt.message!r})"
        )
        assert receipt.applied is False, (
            f"[{note_id}] expected applied is False, got {receipt.applied!r}"
        )
        assert not target.exists(), (
            f"[{note_id}] schema-invalid frontmatter was persisted to {target} "
            "— write path is not gating on validation"
        )
