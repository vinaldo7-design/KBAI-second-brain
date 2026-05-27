"""Tests for write_create_note (kbai/storage/note_creator.py)."""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kbai.storage.note_creator import create_note


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "06-Maps").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _valid_fm(title: str = "Test Note", note_type: str = "idea") -> dict:
    """A frontmatter dict that passes kbai.schema.validate_frontmatter."""
    return {
        "title": title,
        "type": note_type,
        "status": "seedling",
        "summary": "a one-sentence summary",
        "tags": ["topic/test", "lens/academic"],
    }


def test_happy_path_file_created(tmp_path):
    vault = _vault(tmp_path)
    receipt = create_note(
        vault_root=vault,
        folder="01-Ideas",
        note_id="test-note",
        frontmatter=_valid_fm(title="Test Note", note_type="idea"),
        body="## The Idea\nSome content here.",
        dryrun=False,
    )
    assert receipt.status == "applied"
    assert receipt.applied is True
    target = vault / "01-Ideas" / "test-note.md"
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert content.startswith("---\n")
    assert "title: Test Note" in content
    assert "## The Idea" in content
    assert "Some content here." in content


def test_dryrun_no_file_written(tmp_path):
    vault = _vault(tmp_path)
    receipt = create_note(
        vault_root=vault,
        folder="01-Ideas",
        note_id="dry-note",
        frontmatter=_valid_fm(title="Dry Note"),
        body="body text",
        dryrun=True,
    )
    assert receipt.status in ("dryrun", "dry_run")
    assert receipt.applied is False
    assert not (vault / "01-Ideas" / "dry-note.md").exists()


def test_refuses_invalid_folder(tmp_path):
    vault = _vault(tmp_path)
    receipt = create_note(
        vault_root=vault,
        folder="99-Invalid",
        note_id="test-note",
        frontmatter=_valid_fm(),
        body="body",
        dryrun=False,
    )
    assert receipt.status == "error"
    assert receipt.applied is False


def test_refuses_invalid_note_id(tmp_path):
    vault = _vault(tmp_path)
    bad_ids = ["MyNote", "my note", "my_note", "-bad", "bad-", ""]
    for bad_id in bad_ids:
        receipt = create_note(
            vault_root=vault,
            folder="01-Ideas",
            note_id=bad_id,
            frontmatter=_valid_fm(),
            body="body",
            dryrun=False,
        )
        assert receipt.status == "error", f"expected error for note_id={bad_id!r}"
        assert receipt.applied is False


def test_refuses_overwrite_existing(tmp_path):
    vault = _vault(tmp_path)
    folder = vault / "01-Ideas"
    folder.mkdir(parents=True, exist_ok=True)
    existing = folder / "existing-note.md"
    existing.write_text("original content", encoding="utf-8")

    receipt = create_note(
        vault_root=vault,
        folder="01-Ideas",
        note_id="existing-note",
        frontmatter=_valid_fm(title="New"),
        body="new body",
        dryrun=False,
    )
    assert receipt.status == "error"
    assert receipt.applied is False
    assert existing.read_text(encoding="utf-8") == "original content"


def test_hash_after_is_64_char_hex(tmp_path):
    vault = _vault(tmp_path)
    receipt = create_note(
        vault_root=vault,
        folder="01-Ideas",
        note_id="hash-test",
        frontmatter=_valid_fm(title="Hash Test"),
        body="some content",
        dryrun=False,
    )
    assert receipt.status == "applied"
    assert receipt.hash_after is not None
    assert len(receipt.hash_after) == 64
    assert all(c in "0123456789abcdef" for c in receipt.hash_after)


def test_journal_row_written(tmp_path):
    vault = _vault(tmp_path)
    receipt = create_note(
        vault_root=vault,
        folder="01-Ideas",
        note_id="journal-test",
        frontmatter=_valid_fm(title="Journal Test"),
        body="body",
        dryrun=False,
    )
    assert receipt.journal_id is not None

    db_path = vault / "06-Maps" / "write-journal.db"
    assert db_path.exists()
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT * FROM mutations WHERE id = ?", (receipt.journal_id,)
    ).fetchone()
    conn.close()
    assert row is not None
    assert row["tool"] == "write_create_note"
    assert row["note_id"] == "journal-test"
    assert row["status"] == "applied"
    assert row["dryrun"] == 0
