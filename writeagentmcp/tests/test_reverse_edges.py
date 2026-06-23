"""Capture-pipeline Task 2: bidirectional labelled-edge patching.

`write_apply_link_suggestions` (kbai.storage.link_applier.apply_link_suggestions)
is the primary edge-patcher. `patch_section` is now create-if-missing: a valid
headed edge type whose heading is ABSENT in the target note gets the heading
created in canonical taxonomy order and the labelled link inserted under it —
instead of the old "no_section". Untyped / mentioned types still return
no_section.

These tests exercise the pure function (`patch_section`) on synthetic note
strings and the bulk applier (`apply_link_suggestions`) on pytest tmp files.
The real vault is never read or mutated.
"""

import os
import sys
from pathlib import Path

import pytest

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.storage.link_applier import apply_link_suggestions
from kbai.storage.section_patcher import EDGE_ORDER, patch_section


# The 7 canonical headed edge types named in the brief.
CANONICAL_HEADED = [
    "builds-on",
    "builds-toward",
    "contradicts",
    "analogous-to",
    "exemplifies",
    "challenges",
    "operationalises",
]


# A note that carries NONE of the typed-link headings — forces create-if-missing
# down every path. Has a trailing "## Status Log" so the created heading is
# placed before it (Rule 3).
_NOTE_NO_LINK_HEADINGS = """\
# Target Note

## Body
Some prose.

## Status Log
- created
"""

# A note that already carries the early link headings but is missing the later
# ones (challenges / operationalises) — exercises canonical-order insertion
# between existing headings (Rule 1).
_NOTE_PARTIAL_HEADINGS = """\
# Target Note

## Links

### Builds on
-

### Contradicts
-

### Analogous to
-

### Referenced in maps
-

## Status Log
- created
"""


# --- (a) each headed type patches, including create-if-missing -------------

@pytest.mark.parametrize("edge_type", CANONICAL_HEADED)
def test_headed_type_patches_when_heading_present(edge_type):
    """When the heading exists, the link lands under it (status patched)."""
    from kbai.storage.section_patcher import EDGE_HEADING

    heading = EDGE_HEADING[edge_type]
    body = f"# Note\n\n{heading}\n-\n\n## Status Log\n"
    new_text, status = patch_section(body, edge_type, "target-x")
    assert status == "patched", f"{edge_type} returned {status!r}"
    assert "[[target-x]]" in new_text


@pytest.mark.parametrize("edge_type", CANONICAL_HEADED)
def test_headed_type_creates_heading_when_absent(edge_type):
    """The Task 2 fix: a valid headed type whose heading is ABSENT now creates
    the heading and inserts the link, instead of returning no_section."""
    from kbai.storage.section_patcher import EDGE_HEADING

    new_text, status = patch_section(_NOTE_NO_LINK_HEADINGS, edge_type, "rev-target")
    assert status == "patched", f"{edge_type} returned {status!r}, expected patched"
    heading = EDGE_HEADING[edge_type]
    assert heading in new_text, f"{edge_type}: heading {heading!r} not created"
    assert "[[rev-target]]" in new_text
    # Created link section sits before the trailing non-link section.
    assert new_text.index(heading) < new_text.index("## Status Log")


def test_created_heading_respects_canonical_order():
    """A heading created in a note that already has some link headings is
    inserted in canonical taxonomy order, not appended blindly."""
    from kbai.storage.section_patcher import EDGE_HEADING

    # 'challenges' (rank 5) into a note with Builds on / Contradicts / Analogous
    # to / Referenced in maps -> must land after Analogous to, before Referenced.
    new_text, status = patch_section(_NOTE_PARTIAL_HEADINGS, "challenges", "rev")
    assert status == "patched"
    pos_analogous = new_text.index(EDGE_HEADING["analogous-to"])
    pos_challenges = new_text.index(EDGE_HEADING["challenges"])
    pos_referenced = new_text.index(EDGE_HEADING["referenced-in"])
    assert pos_analogous < pos_challenges < pos_referenced


def test_untyped_and_mentioned_still_no_section():
    """section_heading: null types must never materialise a heading."""
    for et in ("untyped", "mentioned"):
        new_text, status = patch_section(_NOTE_NO_LINK_HEADINGS, et, "x")
        assert status == "no_section", f"{et!r} returned {status!r}"
        assert new_text == _NOTE_NO_LINK_HEADINGS  # untouched


def test_unknown_type_still_no_section():
    new_text, status = patch_section(_NOTE_NO_LINK_HEADINGS, "not-a-type", "x")
    assert status == "no_section"
    assert new_text == _NOTE_NO_LINK_HEADINGS


# --- bulk applier on tmp vault (no real vault touched) ---------------------

def _vault(tmp_path: Path) -> Path:
    (tmp_path / "06-Maps").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _make_note(vault: Path, note_id: str, content: str, folder: str = "01-Ideas") -> Path:
    d = vault / folder
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{note_id}.md"
    p.write_text(content, encoding="utf-8")
    return p


# Fresh-skeleton-style new note: carries every headed type (post Step-3
# template coverage). Forward edges land under existing headings.
_NEW_NOTE = """\
# New Capture

> summary

## The Idea
prose

---

## Links

### Builds on
-

### Builds toward
-

### Contradicts
-

### Analogous to
-

### Exemplifies
-

### Challenges
-

### Operationalises
-

### Referenced in maps
-

## Status Log
- created
"""

# Existing target note that LACKS a Challenges heading entirely.
_TARGET_NO_CHALLENGES = """\
# Existing Target

> summary

## The Idea
prose

---

## Links

### Builds on
-

### Contradicts
-

### Analogous to
-

### Referenced in maps
-

## Status Log
- created
"""


# --- (b) acceptance: bidirectional challenges edge -------------------------

def test_acceptance_bidirectional_challenges_edge(tmp_path):
    """A capture with a `challenges` edge into target T whose body LACKS a
    Challenges heading must yield BOTH:
      - the forward edge in the new note's Challenges section, AND
      - the reverse labelled edge under T's freshly created Challenges heading.
    All in ONE write_apply_link_suggestions call."""
    vault = _vault(tmp_path)
    new_note = _make_note(vault, "new-capture", _NEW_NOTE)
    target = _make_note(vault, "existing-target", _TARGET_NO_CHALLENGES)

    result = apply_link_suggestions(
        vault,
        [
            # forward: new note -> target
            {"source": "new-capture", "target": "existing-target", "edge_type": "challenges"},
            # reverse: target -> new note (heading created if absent)
            {"source": "existing-target", "target": "new-capture", "edge_type": "challenges"},
        ],
    )
    data = result.model_dump()

    assert data["status"] == "applied"
    assert data["applied_count"] == 2, data
    assert data["no_section"] == 0, data
    assert data["missing_file"] == 0, data

    new_text = new_note.read_text(encoding="utf-8")
    target_text = target.read_text(encoding="utf-8")

    # forward edge present in the new note under its existing Challenges heading
    assert "### Challenges" in new_text
    assert "[[existing-target]]" in new_text
    fwd_section = new_text[new_text.index("### Challenges"):]
    assert "[[existing-target]]" in fwd_section.split("###", 2)[0] + fwd_section

    # reverse edge: Challenges heading CREATED in target, link under it
    assert "### Challenges" in target_text, "reverse heading not created in target"
    assert "[[new-capture]]" in target_text
    # the reverse link sits under the created Challenges heading
    after_heading = target_text[target_text.index("### Challenges"):]
    assert "[[new-capture]]" in after_heading


def test_acceptance_forward_and_reverse_distinct_types(tmp_path):
    """builds-on forward collapses-pair builds-toward reverse: both directions
    land correctly even when the reverse heading is absent in the target."""
    vault = _vault(tmp_path)
    new_note = _make_note(vault, "new-capture", _NEW_NOTE)
    # target lacks builds-toward heading
    target = _make_note(vault, "existing-target", _TARGET_NO_CHALLENGES)

    result = apply_link_suggestions(
        vault,
        [
            {"source": "new-capture", "target": "existing-target", "edge_type": "builds-on"},
            {"source": "existing-target", "target": "new-capture", "edge_type": "builds-toward"},
        ],
    )
    data = result.model_dump()
    assert data["applied_count"] == 2, data
    assert data["no_section"] == 0, data

    assert "[[existing-target]]" in new_note.read_text(encoding="utf-8")
    target_text = target.read_text(encoding="utf-8")
    assert "### Builds toward" in target_text  # created
    assert "[[new-capture]]" in target_text


# --- (c) idempotency: re-apply is a no-op ----------------------------------

def test_idempotent_reapply_is_already_present(tmp_path):
    """Re-running the same bidirectional pair is a no-op: already_present, no
    duplicate links, files unchanged byte-for-byte."""
    vault = _vault(tmp_path)
    new_note = _make_note(vault, "new-capture", _NEW_NOTE)
    target = _make_note(vault, "existing-target", _TARGET_NO_CHALLENGES)

    suggestions = [
        {"source": "new-capture", "target": "existing-target", "edge_type": "challenges"},
        {"source": "existing-target", "target": "new-capture", "edge_type": "challenges"},
    ]

    first = apply_link_suggestions(vault, suggestions).model_dump()
    assert first["applied_count"] == 2

    new_after_first = new_note.read_bytes()
    target_after_first = target.read_bytes()

    second = apply_link_suggestions(vault, suggestions).model_dump()
    assert second["applied_count"] == 0, second
    assert second["already_present"] == 2, second

    # files unchanged on the second run; links not duplicated
    assert new_note.read_bytes() == new_after_first
    assert target.read_bytes() == target_after_first
    assert target.read_text(encoding="utf-8").count("[[new-capture]]") == 1
    assert new_note.read_text(encoding="utf-8").count("[[existing-target]]") == 1


def test_pure_function_idempotent_create_then_reapply():
    """The pure path: create-if-missing then re-run -> already_present, stable."""
    out1, s1 = patch_section(_NOTE_NO_LINK_HEADINGS, "operationalises", "rev")
    assert s1 == "patched"
    out2, s2 = patch_section(out1, "operationalises", "rev")
    assert s2 == "already_present"
    assert out1 == out2
    assert out2.count("[[rev]]") == 1


# --- sanity: EDGE_ORDER carries the 7 canonical types ----------------------

def test_canonical_headed_types_in_edge_order():
    for et in CANONICAL_HEADED:
        assert et in EDGE_ORDER, f"{et} missing from EDGE_ORDER {EDGE_ORDER}"
