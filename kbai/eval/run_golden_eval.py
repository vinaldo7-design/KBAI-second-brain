"""Run the silver golden-set retrieval eval against the live assemble_context.

Measures the current pipeline (hybrid dense+BM25 seed → PPR → prune) so retrieval
changes (slices 4/5) can be compared to a recorded baseline. The golden set is
SILVER (content-grounded, not user-curated), so this is a measurement + regression
tool, not a hard CI gate.

Usage (from the vault root, with VAULT_ROOT set):
    python -m kbai.eval.run_golden_eval                  # print metrics
    python -m kbai.eval.run_golden_eval --write-baseline # also record baseline
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import yaml

from kbai.eval.metrics import hit_at_k, recall_at_k, reciprocal_rank

_ROOT = Path(__file__).resolve().parent.parent.parent
GOLDEN_PATH = _ROOT / "eval" / "golden_set.yaml"
BASELINE_PATH = _ROOT / "eval" / "baseline.json"


def load_golden(path=GOLDEN_PATH) -> list[dict]:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    return data.get("queries", [])


def evaluate(golden: list[dict], assemble_fn, *, k_recall: int = 10, k_primary: int = 3):
    """Run each query through assemble_fn (query -> ranked note_ids) and score.

    Returns (per_query_rows, summary). Pure given a deterministic assemble_fn —
    the metric maths is unit-tested separately with a fake assemble_fn."""
    rows = []
    for q in golden:
        ranked = assemble_fn(q["query"])
        rows.append({
            "id": q["id"],
            "rr": reciprocal_rank(ranked, q["expected"]),
            "recall": recall_at_k(ranked, q["expected"], k_recall),
            "primary_hit": hit_at_k(ranked, q["primary"], k_primary),
            "top3": ranked[:3],
        })
    n = len(rows) or 1
    summary = {
        "mrr": round(sum(r["rr"] for r in rows) / n, 4),
        f"recall@{k_recall}": round(sum(r["recall"] for r in rows) / n, 4),
        f"primary_hit@{k_primary}": round(sum(r["primary_hit"] for r in rows) / n, 4),
        "n": len(rows),
    }
    return rows, summary


def _live_assemble():
    """assemble_fn bound to the live mini-vinny retrieval pipeline."""
    from minivinnymcp import server as mv

    def assemble(query: str) -> list[str]:
        out = mv._assemble_context_impl(query, seed_k=5, char_budget=0, mode="standard")
        return [n["note_id"] for n in out["notes"]]

    return assemble


def main() -> None:
    golden = load_golden()
    rows, summary = evaluate(golden, _live_assemble())
    for r in rows:
        print(
            f"  {r['id']}  rr={r['rr']:.3f}  recall@10={r['recall']:.2f}  "
            f"primary@3={int(r['primary_hit'])}  top3={r['top3']}"
        )
    print("\nSUMMARY:", json.dumps(summary))
    if "--write-baseline" in sys.argv:
        BASELINE_PATH.write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print(f"baseline written -> {BASELINE_PATH}")


if __name__ == "__main__":
    main()
