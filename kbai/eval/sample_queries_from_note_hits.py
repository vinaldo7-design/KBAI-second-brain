"""Stage 0 item 6: sample candidate golden-set queries from real usage.

Reads `06-Maps/vault-embeddings.db::note_hits` (and `query_log` if present —
populated by Stage 0 item 10's instrumentation module). Ranks query hashes by
recency × surface count and writes a draft JSON file that the user curates.

Limitations (Stage 0):
- note_hits stores query_hash, not text. Once Item 10's `query_log` table
  starts accumulating, this script joins to recover text. Until then, draft
  rows have query_text=null and the user fills them in by hand.

Usage:
    python -m kbai.eval.sample_queries_from_note_hits [--n=30]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Iterable

_VAULT_ROOT = Path(__file__).parent.parent.parent
_DB_PATH = _VAULT_ROOT / "06-Maps" / "vault-embeddings.db"
_OUT_PATH = _VAULT_ROOT / "eval" / "golden_queries.draft.json"


def _table_exists(db: sqlite3.Connection, name: str) -> bool:
    row = db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def sample_query_hashes(db_path: Path = _DB_PATH, n: int = 30) -> list[dict]:
    """Return the top-n query hashes ranked by `surface_count * recency_weight`.
    recency_weight = 1.0 for hits in last 7 days, decays linearly to 0.1 over 90 days.
    """
    if not db_path.exists():
        return []
    db = sqlite3.connect(db_path)
    if not _table_exists(db, "note_hits"):
        db.close()
        return []

    rows = db.execute("SELECT query_hash, ts FROM note_hits").fetchall()
    if not rows:
        db.close()
        return []

    max_ts = max(ts for _, ts in rows)
    counts: dict[str, float] = defaultdict(float)
    last_seen: dict[str, int] = {}
    for qh, ts in rows:
        age_days = max(0.0, (max_ts - ts) / 86400.0)
        recency = 1.0 if age_days <= 7 else max(0.1, 1.0 - (age_days - 7) / 83.0)
        counts[qh] += recency
        last_seen[qh] = max(last_seen.get(qh, 0), ts)

    # Optional: join query text if Item 10's query_log table exists
    text_lookup: dict[str, str] = {}
    if _table_exists(db, "query_log"):
        for qh, qt in db.execute("SELECT query_hash, query_text FROM query_log"):
            if qt:
                text_lookup[qh] = qt
    db.close()

    ranked = sorted(counts.items(), key=lambda x: -x[1])[:n]
    return [
        {
            "id": f"q{i+1:02d}",
            "query_hash": qh,
            "weighted_count": round(score, 3),
            "last_seen_ts": last_seen[qh],
            "query_text": text_lookup.get(qh),  # may be null until Item 10 lands
        }
        for i, (qh, score) in enumerate(ranked)
    ]


def write_draft(samples: Iterable[dict], out_path: Path = _OUT_PATH) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    data = {
        "schema_version": 1,
        "stage": 0,
        "queries": list(samples),
        "note": (
            "Draft sampled from note_hits. Fill query_text manually until "
            "Item 10's query_log accumulates. Rank tier-1/tier-2 expected notes "
            "in a separate file once curated."
        ),
    }
    out_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
    return out_path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--n", type=int, default=30)
    p.add_argument("--db", type=Path, default=_DB_PATH)
    p.add_argument("--out", type=Path, default=_OUT_PATH)
    args = p.parse_args()

    samples = sample_query_hashes(args.db, args.n)
    out = write_draft(samples, args.out)
    print(f"Sampled {len(samples)} query hashes → {out}")


if __name__ == "__main__":
    main()
