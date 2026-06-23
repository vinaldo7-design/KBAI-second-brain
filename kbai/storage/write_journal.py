"""Stage 3 item 4: SQLite write journal.

Every Write Agent mutation appends one row here, BEFORE the receipt is
returned. The journal is the single source of truth for "what did the
write-agent do and when".

DB path: <vault_root>/06-Maps/write-journal.db

Schema (table `mutations`):
  id            INTEGER PRIMARY KEY AUTOINCREMENT
  ts            TEXT  -- ISO 8601 UTC
  tool          TEXT  -- write_create_note | write_apply_link_suggestions | frontmatter_migrate
  note_id       TEXT  -- single note_id when applicable; else "" or bulk descriptor
  file          TEXT  -- vault-relative path (or absolute fallback)
  hash_before   TEXT  -- SHA-256 of pre-write file bytes (NULL for new-file create)
  hash_after    TEXT  -- SHA-256 of post-write file bytes
  status        TEXT  -- applied | dry_run | already_present | no_section | missing_file | error
  dryrun        INTEGER  -- 0/1
  payload_json  TEXT  -- arbitrary tool-specific payload, JSON-encoded
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path


_SCHEMA = """
CREATE TABLE IF NOT EXISTS mutations (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    ts           TEXT NOT NULL,
    tool         TEXT NOT NULL,
    note_id      TEXT,
    file         TEXT,
    hash_before  TEXT,
    hash_after   TEXT,
    status       TEXT NOT NULL,
    dryrun       INTEGER NOT NULL DEFAULT 0,
    payload_json TEXT NOT NULL DEFAULT '{}'
);
"""


def get_db_path(vault_root: Path) -> Path:
    """Return canonical path to the write journal DB for this vault."""
    return Path(vault_root) / "06-Maps" / "write-journal.db"


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create the mutations table if it does not exist. Idempotent."""
    conn.executescript(_SCHEMA)
    conn.commit()


def _connect(vault_root: Path) -> sqlite3.Connection:
    db_path = get_db_path(vault_root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    ensure_schema(conn)
    return conn


def record_mutation(
    vault_root: Path,
    tool: str,
    note_id: str | None,
    file: str | None,
    hash_before: str | None,
    hash_after: str | None,
    status: str,
    dryrun: bool,
    payload_json: str = "{}",
) -> int:
    """Append one mutation row. Returns the newly assigned journal id."""
    conn = _connect(vault_root)
    try:
        ts = datetime.now(timezone.utc).isoformat()
        cur = conn.execute(
            """INSERT INTO mutations
               (ts, tool, note_id, file, hash_before, hash_after, status, dryrun, payload_json)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (
                ts,
                tool,
                note_id or "",
                file or "",
                hash_before,
                hash_after,
                status,
                1 if dryrun else 0,
                payload_json or "{}",
            ),
        )
        conn.commit()
        return int(cur.lastrowid)
    finally:
        conn.close()


def last_n(vault_root: Path, n: int = 20) -> list[dict]:
    """Return the last `n` mutation rows, newest first."""
    conn = _connect(vault_root)
    try:
        rows = conn.execute(
            "SELECT * FROM mutations ORDER BY id DESC LIMIT ?", (int(n),)
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
