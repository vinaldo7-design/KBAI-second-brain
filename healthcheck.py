#!/usr/bin/env python3
"""
healthcheck.py — Fail loudly when a search layer silently returns nothing.

Two independent search paths feed mini-vinny, and both can fail *silently* —
returning an empty list (or an opaque tool-call error) while the vault and the
file API still look perfectly healthy:

  1. Semantic — local sqlite-vec index, queried by minivinnymcp/server.py
  2. Text     — Obsidian Local REST API plugin, queried by the obsidian MCP

A silent empty is the worst failure mode: obsidian_list_files_in_vault keeps
working (it walks the filesystem), so nothing looks broken until a retrieval
quietly returns 0 and you stall mid-task trying to capture a non-existent stack
trace. This script turns that into an explicit, non-zero-exit assertion:

    "index returned 0 for known-present term"

The sentinel terms are chosen *from the index itself* (a note id that provably
has a vector), so the check can never go stale when a note is renamed.

Run it after re-embedding, after restarting Obsidian, or from cron/CI:

    python healthcheck.py             # check both layers
    python healthcheck.py --semantic  # semantic only (no Obsidian needed)
    python healthcheck.py --text      # text/REST only (skips the model load)

Exit 0 = every checked layer returned hits for a known-present term.
Exit 1 = at least one layer is silently empty or erroring (details printed).

Read-only: never writes to the index or the vault.
"""

import argparse
import json
import os
import ssl
import sys
import urllib.parse
import urllib.request
from pathlib import Path

# Resolve the vault root exactly the way minivinnymcp/server.py does — env var
# first (that is what Claude Desktop injects), then the script's own directory
# as a sensible default for a plain `python healthcheck.py`.
VAULT_ROOT = Path(os.environ.get("VAULT_ROOT") or Path(__file__).parent)
DB_PATH = VAULT_ROOT / "06-Maps" / "vault-embeddings.db"

# The user's own canonical notes — used as sentinels when present, so the output
# names a term they recognise. Falls back to whatever the index actually holds.
PREFERRED_SENTINELS = (
    "tacit-knowledge-escapes-legibility",
    "merleau-ponty-bodily-knowing",
)

GREEN, RED, DIM, RESET = "\033[32m", "\033[31m", "\033[2m", "\033[0m"


def _ok(msg: str) -> None:
    print(f"{GREEN}  ✓{RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"{RED}  ✗ {msg}{RESET}")


# --------------------------------------------------------------------------- #
# Sentinel selection                                                          #
# --------------------------------------------------------------------------- #
def pick_sentinel(db) -> tuple[str, str]:
    """Return (note_id, query_text) for a note that provably has a vector.

    note_id   — exact string known to exist in the vault (its own filename/links),
                used for the text-search assertion.
    query_text— the note's title (or summary), used for the semantic assertion;
                a natural phrase guaranteed to be relevant to a present note.
    """
    have_vectors = {
        row[0]
        for row in db.execute("SELECT note_id FROM note_vectors").fetchall()
    }
    if not have_vectors:
        raise RuntimeError(
            f"Embedding index at {DB_PATH} has 0 vectors. Run vault_embed.py."
        )

    # Prefer a recognisable anchor note; otherwise take the note with the
    # longest summary (most substantive, deterministic, rename-safe).
    for nid in PREFERRED_SENTINELS:
        if nid in have_vectors:
            row = db.execute(
                "SELECT title, summary FROM notes WHERE id = ?", (nid,)
            ).fetchone()
            if row:
                title, summary = row
                return nid, (title or summary or nid)

    nid, title, summary = db.execute(
        """
        SELECT n.id, n.title, n.summary
        FROM notes n JOIN note_vectors v ON v.note_id = n.id
        ORDER BY LENGTH(n.summary) DESC
        LIMIT 1
        """
    ).fetchone()
    return nid, (title or summary or nid)


# --------------------------------------------------------------------------- #
# Layer 1 — semantic (local sqlite-vec index)                                 #
# --------------------------------------------------------------------------- #
def check_semantic() -> bool:
    """Assert the local vector index returns >0 hits for a known-present note.

    Mirrors minivinnymcp/server.py:_vault_search_impl exactly (same model, same
    QUERY_PREFIX, same sqlite-vec MATCH) so a pass here means the MCP tool will
    pass too.
    """
    print("Semantic index (sqlite-vec):")

    if not DB_PATH.exists():
        _fail(f"index file missing: {DB_PATH}")
        _fail("→ run: python vault_embed.py")
        return False

    try:
        from kbai.embed.indexer import open_db
        from vault_search import MODEL_NAME, QUERY_PREFIX, serialize_embedding
        from sentence_transformers import SentenceTransformer
    except Exception as e:  # noqa: BLE001 — surface the real import failure
        _fail(f"cannot import retrieval stack: {type(e).__name__}: {e}")
        return False

    try:
        db = open_db(DB_PATH)
    except Exception as e:  # noqa: BLE001 — e.g. sqlite_vec extension won't load
        _fail(f"cannot open index (sqlite-vec load failed?): {type(e).__name__}: {e}")
        return False

    try:
        notes_n = db.execute("SELECT COUNT(*) FROM notes").fetchone()[0]
        vecs_n = db.execute("SELECT COUNT(*) FROM note_vectors").fetchone()[0]
        if notes_n == 0 or vecs_n == 0:
            _fail(f"index is empty (notes={notes_n}, vectors={vecs_n})")
            return False
        if notes_n != vecs_n:
            _fail(f"index parity broken: notes={notes_n} but vectors={vecs_n} "
                  "(a partial/aborted embed — run vault_embed.py --rebuild)")
            return False
        _ok(f"{notes_n} notes, {vecs_n} vectors (parity OK)")

        sentinel_id, query_text = pick_sentinel(db)

        model = SentenceTransformer(MODEL_NAME)
        qvec = model.encode(QUERY_PREFIX + query_text, normalize_embeddings=True)
        rows = db.execute(
            """
            SELECT v.note_id, v.distance
            FROM note_vectors v JOIN notes n ON n.id = v.note_id
            WHERE v.embedding MATCH ? AND k = ?
            ORDER BY v.distance
            """,
            (serialize_embedding(qvec), 5),
        ).fetchall()
    except Exception as e:  # noqa: BLE001 — surface a query-time crash, don't mask it
        _fail(f"query raised {type(e).__name__}: {e}")
        return False
    finally:
        db.close()

    # The assertion the whole script exists for.
    if len(rows) == 0:
        _fail(f'INDEX RETURNED 0 for known-present term "{query_text}" '
              f'(sentinel note: {sentinel_id})')
        return False

    hit_ids = [r[0] for r in rows]
    found = sentinel_id in hit_ids
    _ok(f'query "{query_text[:48]}" → {len(rows)} hits '
        f'({"sentinel in top-5" if found else "top: " + hit_ids[0]})')
    return True


# --------------------------------------------------------------------------- #
# Layer 2 — text (Obsidian Local REST API)                                    #
# --------------------------------------------------------------------------- #
def _resolve_obsidian_env() -> dict:
    """API key / host / port, from the shell env first, then the Claude Desktop
    config (where the obsidian MCP actually gets them). The key is never logged."""
    key = os.environ.get("OBSIDIAN_API_KEY")
    host = os.environ.get("OBSIDIAN_HOST", "127.0.0.1")
    port = os.environ.get("OBSIDIAN_PORT")
    if not key:
        cfg_path = (
            Path.home()
            / "Library/Application Support/Claude/claude_desktop_config.json"
        )
        try:
            env = json.loads(cfg_path.read_text())["mcpServers"]["obsidian"]["env"]
            key = env.get("OBSIDIAN_API_KEY")
            host = env.get("OBSIDIAN_HOST", host)
            port = env.get("OBSIDIAN_PORT", port)
        except Exception:  # noqa: BLE001 — config absent/renamed is a soft miss
            pass
    return {"key": key, "host": host, "port": int(port) if port else 27124}


def check_text(sentinel_id: str | None = None) -> bool:
    """Assert the Obsidian REST search endpoint returns >0 hits for a string
    that demonstrably exists in the vault."""
    print("Text search (Obsidian Local REST API):")

    cfg = _resolve_obsidian_env()
    if not cfg["key"]:
        _fail("no OBSIDIAN_API_KEY in env or claude_desktop_config.json")
        return False

    # A string guaranteed present: the sentinel note id appears in its own file
    # (frontmatter title + inbound [[links]]). Derive from the index if not given.
    if sentinel_id is None:
        if DB_PATH.exists():
            try:
                from kbai.embed.indexer import open_db
                db = open_db(DB_PATH)
                sentinel_id, _ = pick_sentinel(db)
                db.close()
            except Exception:  # noqa: BLE001
                sentinel_id = PREFERRED_SENTINELS[0]
        else:
            sentinel_id = PREFERRED_SENTINELS[0]

    base = f"https://{cfg['host']}:{cfg['port']}"
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE  # plugin ships a self-signed cert on localhost

    def _request(path: str, method: str = "GET", body: bytes | None = None):
        req = urllib.request.Request(base + path, data=body, method=method)
        req.add_header("Authorization", f"Bearer {cfg['key']}")
        with urllib.request.urlopen(req, context=ctx, timeout=10) as r:
            return r.status, r.read().decode()

    # Reachability + auth.
    try:
        status, _ = _request("/")
    except Exception as e:  # noqa: BLE001 — Obsidian closed / plugin off / bad port
        _fail(f"REST API unreachable at {base} — is Obsidian running with the "
              f"Local REST API plugin enabled? ({type(e).__name__}: {e})")
        return False
    if status != 200:
        _fail(f"REST API at {base}/ returned HTTP {status} (check the API key)")
        return False
    _ok(f"REST API reachable at {base} (HTTP 200)")

    # The assertion.
    try:
        q = urllib.parse.quote(sentinel_id)
        status, raw = _request(f"/search/simple/?query={q}", method="POST", body=b"")
        results = json.loads(raw)
    except Exception as e:  # noqa: BLE001
        _fail(f"/search/simple/ raised {type(e).__name__}: {e}")
        return False

    if not isinstance(results, list) or len(results) == 0:
        _fail(f'SEARCH RETURNED 0 for known-present term "{sentinel_id}" — '
              "Obsidian's internal search index is likely stale. Fix: focus the "
              "Obsidian window, or run 'Reload app without saving' (Cmd+P), then "
              "wait for reindex. (obsidian_list_files_in_vault will still work — "
              "it does not use the search index.)")
        return False

    _ok(f'search "{sentinel_id}" → {len(results)} file(s)')
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--semantic", action="store_true",
                        help="check only the local semantic index")
    parser.add_argument("--text", action="store_true",
                        help="check only the Obsidian REST text search")
    args = parser.parse_args()

    do_semantic = args.semantic or not args.text
    do_text = args.text or not args.semantic

    print(f"{DIM}mini-vinny healthcheck — VAULT_ROOT={VAULT_ROOT}{RESET}\n")

    results = []
    if do_semantic:
        results.append(check_semantic())
        print()
    if do_text:
        results.append(check_text())
        print()

    if all(results):
        print(f"{GREEN}HEALTHCHECK PASSED — every checked layer returned hits.{RESET}")
        return 0
    print(f"{RED}HEALTHCHECK FAILED — a search layer is silently empty or erroring "
          f"(see ✗ above).{RESET}")
    return 1


if __name__ == "__main__":
    sys.exit(main())
