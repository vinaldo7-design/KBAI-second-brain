"""Stage 0 item 10: single instrumentation entry point.

Two writers, both best-effort (never raise — instrumentation must not break
the retrieval pipeline):

1. `record_note_hits(...)` — writes to the existing `note_hits` table
   (schema unchanged from prior _record_hits behaviour).

2. `log_retrieval_event(...)` — writes a richer per-call row to a new
   `retrieval_events` table, AND captures query text into `query_log`
   so the golden-set sampler (item 6) can recover queries by hash.

The `query_log` table is a small additive table — nothing else writes to
note_hits's schema. Stage 1 will move `note_hits` out of the embedding DB
into its own instrumentation DB.
"""

from __future__ import annotations

import hashlib
import sqlite3
import time
from pathlib import Path
from typing import Iterable


_NOTE_HITS_DDL = """
CREATE TABLE IF NOT EXISTS note_hits (
    query_hash TEXT,
    note_id    TEXT,
    rank       INTEGER,
    mode       TEXT,
    ts         INTEGER
)
"""

_QUERY_LOG_DDL = """
CREATE TABLE IF NOT EXISTS query_log (
    query_hash  TEXT PRIMARY KEY,
    query_text  TEXT,
    first_seen  INTEGER,
    last_seen   INTEGER,
    seen_count  INTEGER DEFAULT 1
)
"""

_RETRIEVAL_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS retrieval_events (
    ts                 INTEGER,
    query_hash         TEXT,
    mode               TEXT,
    latency_ms         REAL,
    num_candidates     INTEGER,
    graph_nodes_touched INTEGER,
    top_note_ids       TEXT
)
"""


def _hash_query(query: str) -> str:
    return hashlib.md5(query.encode("utf-8")).hexdigest()[:12]


def record_note_hits(
    db_path: Path | str,
    *,
    query: str,
    results: Iterable[dict],
    mode: str,
) -> None:
    """Append per-note hit rows. Schema-compatible with the legacy
    _record_hits writer in minivinnymcp/server.py."""
    qh = _hash_query(query)
    ts = int(time.time())
    try:
        db = sqlite3.connect(str(db_path))
        db.execute(_NOTE_HITS_DDL)
        db.executemany(
            "INSERT INTO note_hits VALUES (?,?,?,?,?)",
            [(qh, r["note_id"], i, mode, ts) for i, r in enumerate(results)],
        )
        # Also record the text→hash mapping so golden-set sampling can recover it.
        db.execute(_QUERY_LOG_DDL)
        db.execute(
            """INSERT INTO query_log(query_hash, query_text, first_seen, last_seen, seen_count)
               VALUES(?,?,?,?,1)
               ON CONFLICT(query_hash) DO UPDATE SET
                   last_seen=excluded.last_seen,
                   seen_count=query_log.seen_count + 1""",
            (qh, query, ts, ts),
        )
        db.commit()
        db.close()
    except Exception:
        pass  # never block retrieval on instrumentation failure


def log_retrieval_event(
    db_path: Path | str,
    *,
    query: str,
    mode: str,
    latency_ms: float,
    num_candidates: int,
    graph_nodes_touched: int,
    top_note_ids: list[str],
) -> None:
    """Append a richer per-call retrieval event row. Best-effort."""
    qh = _hash_query(query)
    ts = int(time.time())
    try:
        db = sqlite3.connect(str(db_path))
        db.execute(_RETRIEVAL_EVENTS_DDL)
        db.execute(
            "INSERT INTO retrieval_events VALUES (?,?,?,?,?,?,?)",
            (ts, qh, mode, float(latency_ms), int(num_candidates),
             int(graph_nodes_touched), ",".join(top_note_ids)),
        )
        db.commit()
        db.close()
    except Exception:
        pass
