"""Phase 4: kbai.schema is the single source of truth for frontmatter shape.

The validator's accept/reject behavior is derived from the schema module's
constants — never hardcoded. This file pins both the happy path and every
required broken case the brief calls out, plus drift-detector tests in the
shape of Phase 3 (assert the validator's allowed-value sets exactly equal
the schema's source sets).

The write-path integration tests also live here — create_note must return
WriteReceipt(status='error', message=reason) without touching write_text.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kbai import schema
from kbai.schema import (
    ALLOWED_LENSES,
    ALLOWED_LIFECYCLE_STAGES,
    ALLOWED_ORIGINS,
    ALLOWED_STATUSES,
    ALLOWED_TYPES,
    ORIGIN_TYPES,
    REQUIRED_FRONTMATTER,
    TAG_PREFIX_LENS,
    TAG_PREFIX_TOPIC,
    allowed_keys,
    validate_frontmatter,
)
from kbai.storage.note_creator import create_note


def _valid_fm() -> dict:
    """Canonical valid frontmatter — every required field, allowed values."""
    return {
        "id": "202605271215",
        "title": "Some Note Title",
        "created": "2026-05-27",
        "updated": "2026-05-27",
        "type": "idea",
        "status": "seedling",
        "summary": "A one-sentence summary.",
        "tags": ["topic/governance", "lens/strategic"],
    }


# --- direct validator behavior -------------------------------------------


def test_valid_frontmatter_passes():
    assert validate_frontmatter(_valid_fm()) is None


def test_id_missing_fails():
    fm = _valid_fm()
    del fm["id"]
    err = validate_frontmatter(fm)
    assert err is not None
    assert "id" in err.lower()


def test_id_equal_to_title_fails():
    fm = _valid_fm() | {"id": "same-string", "title": "same-string"}
    err = validate_frontmatter(fm)
    assert err is not None
    assert "id" in err.lower() and "title" in err.lower()


def test_summary_missing_fails():
    fm = _valid_fm()
    del fm["summary"]
    err = validate_frontmatter(fm)
    assert err is not None
    # Could be flagged by either required-fields check or summary check.
    assert "summary" in err.lower() or "required" in err.lower()


def test_summary_empty_string_fails():
    fm = _valid_fm() | {"summary": ""}
    err = validate_frontmatter(fm)
    assert err is not None
    assert "summary" in err.lower()


def test_summary_whitespace_only_fails():
    fm = _valid_fm() | {"summary": "   "}
    err = validate_frontmatter(fm)
    assert err is not None
    assert "summary" in err.lower()


def test_bad_status_fails():
    fm = _valid_fm() | {"status": "draft"}
    err = validate_frontmatter(fm)
    assert err is not None
    assert "status" in err.lower()


def test_bad_lens_fails():
    fm = _valid_fm() | {"tags": ["topic/foo", "lens/not-a-real-lens"]}
    err = validate_frontmatter(fm)
    assert err is not None
    assert "lens" in err.lower()


def test_bad_type_fails():
    fm = _valid_fm() | {"type": "thinker"}
    err = validate_frontmatter(fm)
    assert err is not None
    assert "type" in err.lower()


def test_tag_without_prefix_fails():
    fm = _valid_fm() | {"tags": ["just-a-tag-no-prefix"]}
    err = validate_frontmatter(fm)
    assert err is not None
    assert "topic/" in err or "lens/" in err


def test_required_field_missing_fails():
    fm = _valid_fm()
    del fm["type"]
    err = validate_frontmatter(fm)
    assert err is not None
    assert "required" in err.lower() or "type" in err.lower()


def test_tags_not_a_list_fails():
    fm = _valid_fm() | {"tags": "topic/wrong"}
    err = validate_frontmatter(fm)
    assert err is not None
    assert "tags" in err.lower()


# --- drift detectors (Phase 3 pattern) -----------------------------------


def test_drift_allowed_statuses_accept_set_equals_schema():
    """For every status in schema.ALLOWED_STATUSES, validator accepts.
    For every status outside, validator rejects with a status-specific error.
    Asserts the validator's effective set IS exactly the schema's set."""
    for st in ALLOWED_STATUSES:
        assert validate_frontmatter(_valid_fm() | {"status": st}) is None, (
            f"validator rejected schema-allowed status {st!r}"
        )
    for st in ("draft", "processing", "unprocessed", "archived", "WIP", ""):
        if st in ALLOWED_STATUSES:
            continue
        err = validate_frontmatter(_valid_fm() | {"status": st})
        assert err is not None and "status" in err.lower(), (
            f"validator accepted non-schema status {st!r}"
        )


def test_drift_allowed_types_accept_set_equals_schema():
    for nt in ALLOWED_TYPES:
        assert validate_frontmatter(_valid_fm() | {"type": nt}) is None, (
            f"validator rejected schema-allowed type {nt!r}"
        )
    for nt in ("thinker", "draft", "todo", "quick-capture", ""):
        if nt in ALLOWED_TYPES:
            continue
        err = validate_frontmatter(_valid_fm() | {"type": nt})
        assert err is not None and "type" in err.lower(), (
            f"validator accepted non-schema type {nt!r}"
        )


def test_drift_allowed_lenses_accept_set_equals_schema():
    for lens in ALLOWED_LENSES:
        fm = _valid_fm() | {"tags": ["topic/foo", f"{TAG_PREFIX_LENS}{lens}"]}
        assert validate_frontmatter(fm) is None, (
            f"validator rejected schema-allowed lens {lens!r}"
        )
    for lens in ("operational", "design", "casual", "engineer", ""):
        if lens in ALLOWED_LENSES:
            continue
        fm = _valid_fm() | {"tags": ["topic/foo", f"{TAG_PREFIX_LENS}{lens}"]}
        err = validate_frontmatter(fm)
        assert err is not None and "lens" in err.lower(), (
            f"validator accepted non-schema lens {lens!r}"
        )


def test_drift_allowed_lifecycle_stages_accept_set_equals_schema():
    """lifecycle_stage is optional. When present-and-non-null, the value must
    be in ALLOWED_LIFECYCLE_STAGES; otherwise the validator ignores it."""
    # Absent → valid.
    fm = _valid_fm()
    assert "lifecycle_stage" not in fm
    assert validate_frontmatter(fm) is None
    # Explicit None → valid (treated as absent).
    assert validate_frontmatter(_valid_fm() | {"lifecycle_stage": None}) is None
    # Every schema-allowed value → valid.
    for stage in ALLOWED_LIFECYCLE_STAGES:
        assert (
            validate_frontmatter(_valid_fm() | {"lifecycle_stage": stage}) is None
        ), f"validator rejected schema-allowed lifecycle_stage {stage!r}"
    # Anything not in the set → rejected with a lifecycle_stage-specific error.
    for bad in ("seedling", "evergreen", "nonsense", "WIP"):
        if bad in ALLOWED_LIFECYCLE_STAGES:
            continue
        err = validate_frontmatter(_valid_fm() | {"lifecycle_stage": bad})
        assert err is not None and "lifecycle_stage" in err.lower(), (
            f"validator accepted non-schema lifecycle_stage {bad!r}"
        )


def test_drift_required_fields_exactly_match_schema():
    """For each field in REQUIRED_FRONTMATTER, removing it from an otherwise-
    valid dict must produce an error. No other field omission can pass either,
    asserting that the validator's required set is exactly schema's set."""
    base = _valid_fm()
    for field in REQUIRED_FRONTMATTER:
        fm = {k: v for k, v in base.items() if k != field}
        err = validate_frontmatter(fm)
        assert err is not None, (
            f"validator accepted frontmatter missing schema-required field {field!r}"
        )


def test_drift_schema_module_has_no_duplicate_source_of_truth():
    """note_creator must not redeclare any schema constant locally — the
    Phase 3 lesson: drift between writer-side and parser-side hardcoded sets."""
    from kbai.storage import note_creator
    for name in (
        "REQUIRED_FRONTMATTER", "DEPRECATED_FRONTMATTER",
        "ALLOWED_STATUSES", "ALLOWED_TYPES", "ALLOWED_LENSES",
    ):
        assert not hasattr(note_creator, name) or getattr(note_creator, name) is getattr(schema, name, None), (
            f"note_creator redefines {name} — must import from kbai.schema instead"
        )


# --- write-path integration: validator gates write_text ------------------


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "06-Maps").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_create_note_rejects_id_equal_title(tmp_path):
    vault = _vault(tmp_path)
    fm = _valid_fm() | {"id": "same", "title": "same"}
    receipt = create_note(
        vault_root=vault, folder="01-Ideas", note_id="some-note",
        frontmatter=fm, body="body", dryrun=False,
    )
    assert receipt.status == "error"
    assert receipt.applied is False
    assert "id" in (receipt.message or "").lower()
    # No file written.
    assert not (vault / "01-Ideas" / "some-note.md").exists()


def test_create_note_rejects_missing_summary(tmp_path):
    vault = _vault(tmp_path)
    fm = _valid_fm()
    del fm["summary"]
    receipt = create_note(
        vault_root=vault, folder="01-Ideas", note_id="no-summary",
        frontmatter=fm, body="body", dryrun=False,
    )
    assert receipt.status == "error"
    assert receipt.applied is False
    assert not (vault / "01-Ideas" / "no-summary.md").exists()


def test_create_note_rejects_bad_status(tmp_path):
    vault = _vault(tmp_path)
    fm = _valid_fm() | {"status": "draft"}
    receipt = create_note(
        vault_root=vault, folder="01-Ideas", note_id="bad-status",
        frontmatter=fm, body="body", dryrun=False,
    )
    assert receipt.status == "error"
    assert "status" in (receipt.message or "").lower()
    assert not (vault / "01-Ideas" / "bad-status.md").exists()


def test_create_note_rejects_bad_lens(tmp_path):
    vault = _vault(tmp_path)
    fm = _valid_fm() | {"tags": ["topic/x", "lens/operational"]}
    receipt = create_note(
        vault_root=vault, folder="01-Ideas", note_id="bad-lens",
        frontmatter=fm, body="body", dryrun=False,
    )
    assert receipt.status == "error"
    assert "lens" in (receipt.message or "").lower()
    assert not (vault / "01-Ideas" / "bad-lens.md").exists()


def test_create_note_valid_passes_through(tmp_path):
    vault = _vault(tmp_path)
    receipt = create_note(
        vault_root=vault, folder="01-Ideas", note_id="valid-note",
        frontmatter=_valid_fm(), body="## Body", dryrun=False,
    )
    assert receipt.status == "applied"
    assert receipt.applied is True
    assert (vault / "01-Ideas" / "valid-note.md").exists()


# --- Task 4: strengthened validator (created/updated, project, origin, unknown-key) ---


def test_created_and_updated_now_required():
    for field in ("created", "updated"):
        fm = {k: v for k, v in _valid_fm().items() if k != field}
        err = validate_frontmatter(fm)
        assert err is not None and ("required" in err.lower() or field in err.lower()), (
            f"validator accepted frontmatter missing {field!r}"
        )


def test_project_type_passes():
    assert validate_frontmatter(_valid_fm() | {"type": "project"}) is None


def test_wrong_case_type_fails():
    err = validate_frontmatter(_valid_fm() | {"type": "Learning"})
    assert err is not None and "type" in err.lower()


def test_summary_non_string_fails():
    err = validate_frontmatter(_valid_fm() | {"summary": {"summary": None}})
    assert err is not None and "summary" in err.lower()


def test_unknown_key_rejected():
    err = validate_frontmatter(_valid_fm() | {"medium": "lecture"})
    assert err is not None
    assert "medium" in err.lower()


def test_origin_valid_on_idea_passes():
    assert validate_frontmatter(_valid_fm() | {"origin": "lecture"}) is None


def test_origin_off_enum_fails():
    err = validate_frontmatter(_valid_fm() | {"origin": "podcast"})
    assert err is not None and "origin" in err.lower()


def test_origin_on_concept_fails():
    err = validate_frontmatter(_valid_fm() | {"type": "concept", "origin": "conversation"})
    assert err is not None and "origin" in err.lower()


def test_capture_with_origin_passes():
    # capture IS an origin-type — the /capture command writes origin: conversation.
    assert validate_frontmatter(
        _valid_fm() | {"type": "capture", "origin": "conversation"}
    ) is None


def test_learning_extensions_pass():
    fm = _valid_fm() | {
        "type": "learning", "origin": "lecture",
        "author": "Some Author", "context": "Oxford DipAI",
    }
    assert validate_frontmatter(fm) is None


def test_learning_extensions_rejected_on_idea():
    err = validate_frontmatter(_valid_fm() | {"author": "Some Author"})
    assert err is not None and "author" in err.lower()


# --- drift detectors for the new sets ---


def test_drift_allowed_origins_accept_set_equals_schema():
    for org in ALLOWED_ORIGINS:
        assert validate_frontmatter(_valid_fm() | {"origin": org}) is None, (
            f"validator rejected schema-allowed origin {org!r}"
        )
    for org in ("podcast", "video", "tweet", "blog"):
        if org in ALLOWED_ORIGINS:
            continue
        err = validate_frontmatter(_valid_fm() | {"origin": org})
        assert err is not None and "origin" in err.lower()


def test_drift_origin_only_on_origin_types():
    for nt in ALLOWED_TYPES:
        err = validate_frontmatter(_valid_fm() | {"type": nt, "origin": "conversation"})
        if nt in ORIGIN_TYPES:
            assert err is None, f"origin rejected on origin-type {nt!r}: {err}"
        else:
            assert err is not None and "origin" in err.lower(), (
                f"origin accepted on non-origin-type {nt!r}"
            )


def test_allowed_keys_composition_matches_schema():
    from kbai.schema import SHARED_OPTIONAL, TYPE_EXTENSIONS
    for nt in ALLOWED_TYPES:
        ak = allowed_keys(nt)
        assert REQUIRED_FRONTMATTER <= ak
        assert SHARED_OPTIONAL <= ak
        assert ("origin" in ak) == (nt in ORIGIN_TYPES)
        assert TYPE_EXTENSIONS.get(nt, frozenset()) <= ak
