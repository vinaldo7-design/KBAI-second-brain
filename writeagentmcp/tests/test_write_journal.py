"""Tests for kbai/storage/write_journal.py."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kbai.storage.write_journal import ensure_schema, last_n, record_mutation

import sqlite3


def _make_db(tmp_path: Path):
    db = tmp_path / "write-journal.db"
    conn = sqlite3.connect(str(db))
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    conn.close()
    return db


def _vault(tmp_path: Path) -> Path:
    maps_dir = tmp_path / "06-Maps"
    maps_dir.mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_schema_creates_table(tmp_path):
    db = _make_db(tmp_path)
    conn = sqlite3.connect(str(db))
    tables = {
        r[0]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    conn.close()
    assert "mutations" in tables


def test_record_mutation_returns_int(tmp_path):
    vault = _vault(tmp_path)
    row_id = record_mutation(
        vault_root=vault,
        tool="write_create_note",
        note_id="test-note",
        file="01-Notes/test-note.md",
        hash_before=None,
        hash_after="abc123",
        status="applied",
        dryrun=False,
    )
    assert isinstance(row_id, int)
    assert row_id >= 1


def test_last_n_descending_order(tmp_path):
    vault = _vault(tmp_path)
    for i in range(3):
        record_mutation(
            vault_root=vault,
            tool="write_create_note",
            note_id=f"note-{i}",
            file=f"01-Notes/note-{i}.md",
            hash_before=None,
            hash_after=f"hash{i}",
            status="applied",
            dryrun=False,
        )
    rows = last_n(vault, n=20)
    assert len(rows) == 3
    ids = [r["id"] for r in rows]
    assert ids == sorted(ids, reverse=True)


def test_dryrun_stored_as_int(tmp_path):
    vault = _vault(tmp_path)
    id_true = record_mutation(
        vault_root=vault,
        tool="write_create_note",
        note_id="dry-note",
        file="01-Notes/dry-note.md",
        hash_before=None,
        hash_after="xyz",
        status="dry_run",
        dryrun=True,
    )
    id_false = record_mutation(
        vault_root=vault,
        tool="write_create_note",
        note_id="real-note",
        file="01-Notes/real-note.md",
        hash_before=None,
        hash_after="xyz",
        status="applied",
        dryrun=False,
    )
    rows = {r["id"]: r for r in last_n(vault, n=10)}
    assert rows[id_true]["dryrun"] == 1
    assert rows[id_false]["dryrun"] == 0
