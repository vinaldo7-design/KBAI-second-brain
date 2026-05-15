"""Top-level imagination entry point.

Combines signature extraction + prompt building into a single
ImaginationEvidence bundle. The bundle is what Claude consumes via the
/imagine slash command — same pattern as CouncilEvidence + /council.
"""

from __future__ import annotations

from typing import Any

from vault_graph_loader import VaultGraph

from kbai.imagination.prompts import MODES, build_synthesis_prompt
from kbai.imagination.signature import extract_cluster_signature


def imagine(
    graph: VaultGraph,
    seed: str,
    mode: str = "fracture",
    depth: int = 2,
    k: int = 5,
) -> dict[str, Any]:
    """Build an ImaginationEvidence bundle for the given seed + mode.

    Args:
        graph: a loaded VaultGraph
        seed: anchor note_id (or map id)
        mode: one of MODES — extend | fracture | bridge | deepen | historicise
        depth: BFS hops included in the cluster signature (default 2)
        k: number of domains to request from the synthesizer (default 5)

    Returns a dict with:
        - seed, mode, k, depth
        - cluster_signature (the structural fingerprint)
        - synthesis_prompt (Claude-ready prompt for the slash command)
        - error (if any)
    """
    if mode not in MODES:
        return {
            "seed": seed,
            "mode": mode,
            "error": f"unknown mode '{mode}' — pick one of {list(MODES)}",
        }

    signature = extract_cluster_signature(graph, seed, depth)
    if "error" in signature:
        return {
            "seed": seed,
            "mode": mode,
            "k": k,
            "depth": depth,
            "cluster_signature": signature,
            "error": signature["error"],
        }

    prompt = build_synthesis_prompt(signature, mode, k=k)
    return {
        "seed": seed,
        "mode": mode,
        "k": k,
        "depth": depth,
        "cluster_signature": signature,
        "synthesis_prompt": prompt,
    }
