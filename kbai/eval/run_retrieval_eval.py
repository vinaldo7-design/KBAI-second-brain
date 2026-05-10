"""Stage 0 item 7: stub retrieval-eval runner.

Loads queries from `eval/golden_queries.draft.json` (or whichever JSON path is
passed) and prints `query_id | mode | top-5 ids | latency_ms` per row.

No metrics, no thresholds — Stage 6 wires those in. Stage 0 just proves the
plumbing.

Usage:
    python -m kbai.eval.run_retrieval_eval [--queries=path] [--mode=standard]
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

_VAULT_ROOT = Path(__file__).parent.parent.parent
_DEFAULT_QUERIES = _VAULT_ROOT / "eval" / "golden_queries.draft.json"


def _load_queries(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("queries", [])


def run_one(query_text: str, mode: str = "standard") -> dict:
    """Call the retrieval pipeline once. Imported lazily to avoid hard
    dependency on sentence-transformers when the runner is invoked in --dry mode."""
    import os, sys
    os.environ.setdefault("VAULT_ROOT", str(_VAULT_ROOT))
    sys.path.insert(0, str(_VAULT_ROOT))
    from minivinnymcp.server import _assemble_context_impl

    t0 = time.perf_counter()
    result = _assemble_context_impl(query_text, seed_k=5, char_budget=2000, mode=mode)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    top_ids = [n["note_id"] for n in result.get("notes", [])[:5]]
    return {
        "mode": mode,
        "top_ids": top_ids,
        "latency_ms": round(latency_ms, 1),
        "n_returned": len(result.get("notes", [])),
    }


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--queries", type=Path, default=_DEFAULT_QUERIES)
    p.add_argument("--mode", default="standard", choices=("standard", "sparring", "exhaustive"))
    p.add_argument("--dry", action="store_true",
                   help="Don't run retrieval — just print loaded query rows.")
    args = p.parse_args()

    queries = _load_queries(args.queries)
    if not queries:
        print(f"No queries at {args.queries}. Run sample_queries_from_note_hits first.")
        return 0

    print(f"# {len(queries)} queries loaded from {args.queries}")
    for q in queries:
        qid = q.get("id", "?")
        text = q.get("query_text")
        if not text:
            print(f"{qid}\t(no query_text — fill in to evaluate)")
            continue
        if args.dry:
            print(f"{qid}\t[dry] {text[:60]!r}")
            continue
        try:
            r = run_one(text, mode=args.mode)
        except Exception as e:  # never break the loop on one query
            print(f"{qid}\tERROR\t{e}")
            continue
        ids = ",".join(r["top_ids"]) or "(none)"
        print(f"{qid}\t{r['mode']}\t{r['latency_ms']:>7}ms\t{ids}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
