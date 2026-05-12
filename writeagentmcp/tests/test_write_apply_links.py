"""Tests for write_apply_link_suggestions (kbai/storage/link_applier.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kbai.storage.link_applier import apply_link_suggestions
from kbai.storage.section_patcher import patch_section  # noqa: F401 — import test


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "06-Maps").mkdir(parents=True, exist_ok=True)
    return tmp_path


_NOTE_TEMPLATE = """\
# Source Note

## Links

### Builds on
-

### Exemplifies
-

### Contradicts
- [[already-here]]
"""


def _make_note(vault: Path, note_id: str, content: str = _NOTE_TEMPLATE) -> Path:
    folder = vault / "01-Ideas"
    folder.mkdir(parents=True, exist_ok=True)
    note = folder / f"{note_id}.md"
    note.write_text(content, encoding="utf-8")
    return note


# --- import verification ---------------------------------------------------

def test_patch_section_importable_from_storage():
    from kbai.storage.section_patcher import patch_section as ps
    assert callable(ps)


# --- happy path ------------------------------------------------------------

def test_patches_note_with_known_section(tmp_path):
    vault = _vault(tmp_path)
    note = _make_note(vault, "source-note")

    result = apply_link_suggestions(
        vault,
        [{"source": "source-note", "target": "target-note", "edge_type": "builds-on"}],
    )
    data = result.model_dump()

    assert data["status"] == "applied"
    assert data["applied_count"] == 1
    assert data["already_present"] == 0
    assert data["no_section"] == 0
    assert data["missing_file"] == 0
    assert data["rejected_count"] == 0
    assert "[[target-note]]" in note.read_text(encoding="utf-8")


def test_new_edge_types_recognised(tmp_path):
    vault = _vault(tmp_path)
    _make_note(vault, "source-note")

    result = apply_link_suggestions(
        vault,
        [{"source": "source-note", "target": "concept-x", "edge_type": "exemplifies"}],
    )
    data = result.model_dump()

    assert data["applied_count"] == 1
    assert "[[concept-x]]" in (vault / "01-Ideas" / "source-note.md").read_text(encoding="utf-8")


# --- already_present -------------------------------------------------------

def test_already_present_count_and_file_unchanged(tmp_path):
    vault = _vault(tmp_path)
    note = _make_note(vault, "source-note")
    original = note.read_bytes()

    result = apply_link_suggestions(
        vault,
        [{"source": "source-note", "target": "already-here", "edge_type": "contradicts"}],
    )
    data = result.model_dump()

    assert data["already_present"] == 1
    assert data["applied_count"] == 0
    assert note.read_bytes() == original


# --- no_section ------------------------------------------------------------

def test_no_section_handled_gracefully(tmp_path):
    vault = _vault(tmp_path)
    note = _make_note(vault, "source-note")
    original = note.read_bytes()

    result = apply_link_suggestions(
        vault,
        [{"source": "source-note", "target": "wherever", "edge_type": "operationalises"}],
    )
    data = result.model_dump()

    assert data["no_section"] == 1
    assert data["applied_count"] == 0
    assert note.read_bytes() == original


# --- missing_file ----------------------------------------------------------

def test_missing_source_file_handled_gracefully(tmp_path):
    vault = _vault(tmp_path)

    result = apply_link_suggestions(
        vault,
        [{"source": "ghost-note", "target": "target", "edge_type": "builds-on"}],
    )
    data = result.model_dump()

    assert data["missing_file"] == 1
    assert data["applied_count"] == 0


# --- rejected (invalid suggestion) ----------------------------------------

def test_invalid_suggestion_counted_as_rejected(tmp_path):
    vault = _vault(tmp_path)

    result = apply_link_suggestions(
        vault,
        [{"edge_type": "builds-on"}],  # missing source and target
    )
    data = result.model_dump()

    assert data["rejected_count"] == 1
    assert data["applied_count"] == 0


# --- dryrun ----------------------------------------------------------------

def test_dryrun_no_files_written_counts_computed(tmp_path):
    vault = _vault(tmp_path)
    note = _make_note(vault, "source-note")
    original = note.read_bytes()

    result = apply_link_suggestions(
        vault,
        [
            {"source": "source-note", "target": "new-link", "edge_type": "builds-on"},
            {"source": "source-note", "target": "already-here", "edge_type": "contradicts"},
            {"source": "ghost-note", "target": "x", "edge_type": "builds-on"},
        ],
        dryrun=True,
    )
    data = result.model_dump()

    assert data["status"] == "dryrun"
    assert data["applied_count"] == 0   # nothing written
    assert data["already_present"] == 1
    assert data["missing_file"] == 1
    assert note.read_bytes() == original  # file untouched
