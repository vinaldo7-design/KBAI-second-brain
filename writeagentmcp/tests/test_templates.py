"""Phase 6a: kbai.templates is the single source of body skeletons.

Drift detectors and write-path integration. The skeleton set, the heading
set, and the status defaults all derive from kbai.schema and
vault_taxonomy.yaml — never hardcoded here.
"""

import re
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kbai.schema import (
    ALLOWED_LIFECYCLE_STAGES,
    ALLOWED_STATUSES,
    ALLOWED_TYPES,
)
from kbai.storage.note_creator import create_note
from kbai.storage.section_patcher import EDGE_HEADING
from kbai.templates import _TEMPLATES_DIR, BODY_SKELETON, render_body


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "06-Maps").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _valid_fm(note_type: str = "idea") -> dict:
    return {
        "title": "Test Title",
        "type": note_type,
        "status": "seedling",
        "summary": "test summary",
        "tags": ["topic/test", "lens/academic"],
    }


# --- drift: skeleton set vs ALLOWED_TYPES --------------------------------


def test_drift_skeleton_set_equals_allowed_types():
    assert set(BODY_SKELETON.keys()) == ALLOWED_TYPES


def test_skeleton_files_one_per_type():
    on_disk = {p.stem for p in _TEMPLATES_DIR.glob("*.md")}
    assert on_disk == ALLOWED_TYPES


# --- drift: link headings ⊆ EDGE_HEADING ---------------------------------


def _extract_h3_headings(body: str) -> list[str]:
    return re.findall(r"^### (.+?)\s*$", body, re.MULTILINE)


def test_drift_skeleton_link_headings_in_edge_heading():
    edge_heading_texts_lower = {v.lower() for v in EDGE_HEADING.values()}
    for note_type, body in BODY_SKELETON.items():
        for h3 in _extract_h3_headings(body):
            full = f"### {h3}".lower()
            assert full in edge_heading_texts_lower, (
                f"{note_type} skeleton has unknown link heading {full!r}; "
                f"valid: {sorted(EDGE_HEADING.values())}"
            )


# --- drift: skeleton frontmatter aligns to schema ------------------------


def _skeleton_frontmatter(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    parts = text.split("---\n", 2)
    return yaml.safe_load(parts[1]) or {}


def test_drift_skeleton_status_in_allowed():
    for path in _TEMPLATES_DIR.glob("*.md"):
        fm = _skeleton_frontmatter(path)
        assert fm["status"] in ALLOWED_STATUSES, (
            f"{path.name}: status {fm['status']!r} not in ALLOWED_STATUSES"
        )


def test_drift_skeleton_type_matches_filename():
    for path in _TEMPLATES_DIR.glob("*.md"):
        fm = _skeleton_frontmatter(path)
        assert fm["type"] in ALLOWED_TYPES, (
            f"{path.name}: type {fm['type']!r} not in ALLOWED_TYPES"
        )
        assert fm["type"] == path.stem, (
            f"{path.name}: type {fm['type']!r} disagrees with filename stem"
        )


def test_drift_skeleton_lifecycle_stage_in_allowed():
    for path in _TEMPLATES_DIR.glob("*.md"):
        fm = _skeleton_frontmatter(path)
        if "lifecycle_stage" in fm and fm["lifecycle_stage"] is not None:
            assert fm["lifecycle_stage"] in ALLOWED_LIFECYCLE_STAGES, (
                f"{path.name}: lifecycle_stage {fm['lifecycle_stage']!r} "
                "not in ALLOWED_LIFECYCLE_STAGES"
            )


# --- render_body behavior ------------------------------------------------


def test_render_body_substitutes_placeholders():
    body = render_body("idea", title="My Title", summary="my summary")
    assert "My Title" in body
    assert "my summary" in body
    assert "{title}" not in body
    assert "{summary}" not in body


def test_render_body_idea_includes_all_link_sections():
    body = render_body("idea", title="T", summary="S")
    for heading in (
        "### Builds on",
        "### Builds toward",
        "### Contradicts",
        "### Analogous to",
        "### Referenced in maps",
    ):
        assert heading in body, f"idea skeleton missing {heading!r}"


def test_render_body_concept_includes_exemplifies():
    body = render_body("concept", title="T", summary="S")
    assert "### Exemplifies" in body
    assert "### Builds on" in body


def test_render_body_unknown_type_raises():
    with pytest.raises(KeyError):
        render_body("thinker", title="T", summary="S")


def test_render_body_handles_empty_strings():
    body = render_body("idea", title="", summary="")
    assert "{title}" not in body
    assert "{summary}" not in body


# --- write-path integration: empty body → skeleton rendered --------------


def test_create_note_empty_body_renders_skeleton(tmp_path):
    vault = _vault(tmp_path)
    receipt = create_note(
        vault_root=vault,
        folder="01-Ideas",
        note_id="skeleton-test",
        frontmatter=_valid_fm("idea") | {"title": "Skeleton Test"},
        body="",
        dryrun=False,
    )
    assert receipt.status == "applied"
    content = (vault / "01-Ideas" / "skeleton-test.md").read_text(encoding="utf-8")
    assert "## The Idea" in content
    assert "### Builds on" in content
    assert "## Status Log" in content
    assert "Skeleton Test" in content
    assert "{title}" not in content
    assert "{summary}" not in content


def test_create_note_nonempty_body_passes_through(tmp_path):
    vault = _vault(tmp_path)
    receipt = create_note(
        vault_root=vault,
        folder="01-Ideas",
        note_id="passthrough-test",
        frontmatter=_valid_fm("idea"),
        body="## Custom Body\nNot the skeleton.",
        dryrun=False,
    )
    assert receipt.status == "applied"
    content = (vault / "01-Ideas" / "passthrough-test.md").read_text(encoding="utf-8")
    assert "## Custom Body" in content
    assert "Not the skeleton." in content
    assert "## The Idea" not in content
    assert "### Builds on" not in content


def test_create_note_empty_body_capture_uses_capture_skeleton(tmp_path):
    """Right skeleton picked by type — capture's body differs from idea's."""
    vault = _vault(tmp_path)
    receipt = create_note(
        vault_root=vault,
        folder="00-Captures",
        note_id="capture-test",
        frontmatter=_valid_fm("capture") | {"title": "Cap Test"},
        body="",
        dryrun=False,
    )
    assert receipt.status == "applied"
    content = (vault / "00-Captures" / "capture-test.md").read_text(encoding="utf-8")
    assert "## Raw" in content
    assert "## Why" in content
    # Capture skeleton has no labelled-link section
    assert "### Builds on" not in content
