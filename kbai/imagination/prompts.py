"""Mode-specific synthesis prompts for /imagine.

Each mode renders a Claude-readable prompt that consumes a ClusterSignature
dict and returns a structured list of proposed research domains. The prompt
is the contract between this module and the LLM — the slash command
/imagine reads the ImaginationEvidence bundle and uses the embedded prompt
to do the actual reasoning.

Five modes, complete compass coverage:

  extend       sideways — what adjacent domain extends the existing direction?
  fracture     adversarial — what would break the cluster's load-bearing nodes?
  bridge       cross-cluster — what connects this cluster to a distant one?
  deepen       downward — what mechanism sits under the abstract claims here?
  historicise  backward — what intellectual lineage does this implicitly inherit?
"""

from __future__ import annotations

from typing import Any

MODES: tuple[str, ...] = ("extend", "fracture", "bridge", "deepen", "historicise")


_MODE_INSTRUCTIONS: dict[str, str] = {
    "extend": (
        "You are extending this cluster sideways. The frontier nodes below are "
        "where the cluster's reasoning currently terminates — pick neighbouring "
        "intellectual domains where similar arguments have been developed but "
        "not yet imported here. Avoid domains the cluster already covers (see "
        "thematic_vocabulary). Each proposed domain should *continue* the "
        "cluster's existing direction, not pivot away from it."
    ),
    "fracture": (
        "You are pressure-testing this cluster adversarially. The load-bearing "
        "nodes below carry high in-degree but low contradicts ratio — they are "
        "doing unexamined work. Pick intellectual traditions, empirical findings, "
        "or rival frameworks that would directly contradict these specific nodes. "
        "Each proposed domain must name (a) which load-bearing node it attacks, "
        "(b) the exact claim it falsifies, (c) the strongest version of the "
        "counter-position — not a strawman."
    ),
    "bridge": (
        "You are finding cross-domain analogues. Identify distant fields (biology, "
        "monetary policy, urban planning, military strategy, ecology, linguistics, "
        "etc.) where the structural pattern in this cluster appears under a "
        "different name. The point is not surface similarity — it is identifying "
        "a domain whose mature literature would let the cluster import "
        "theory the cluster has been reinventing. Each proposed bridge should name "
        "the domain, the structural isomorphism, and the import-ready concept."
    ),
    "deepen": (
        "You are excavating mechanisms beneath the cluster's abstract claims. "
        "The cluster names a phenomenon at a high level — propose research domains "
        "that would explain *how* the phenomenon works at one level of detail "
        "below. The test: each proposed domain should let the cluster move from "
        "'X happens' to 'X happens because of mechanism M, which can be "
        "measured by Y'. Reject domains that are merely adjacent — only accept "
        "those that go one step down the explanatory ladder."
    ),
    "historicise": (
        "You are recovering the cluster's intellectual lineage. The cluster makes "
        "claims that have ancestors — philosophical traditions, historical "
        "debates, prior scientific paradigms — which the cluster implicitly "
        "inherits but never names. Propose research domains that would name "
        "those ancestors. The test: each domain should produce the response 'so "
        "*that's* where this idea actually comes from' — and reveal what the "
        "earlier tradition already worked out that the cluster is reinventing."
    ),
}


_PER_DOMAIN_TEMPLATE = """\
Return a JSON list of {k} proposed domains. Each entry MUST have this shape:

{{
  "title": "<2-5 word domain name>",
  "thesis": "<1-2 sentence claim the domain makes>",
  "fits": "<1 sentence: why this domain matches the {mode} brief>",
  "seed_question": "<a single concrete research question the domain answers>",
  "suggested_note_id": "<kebab-case stub id for the future vault note>",
  "attacks_or_extends": "<note_id from cluster this connects to>",
  "proposed_edge_type": "<one of: builds-on | builds-toward | contradicts | analogous-to>"
}}

Order the list by what would shift the cluster's thinking most. Do not propose \
domains already represented in the cluster (cross-check against member_ids and \
thematic_vocabulary). Be specific — 'systems theory' is not a domain; 'Stafford \
Beer's Viable System Model' is.
"""


_HEADER = """\
You are operating in /imagine {mode} mode over a cluster of the user's vault.

## Mode brief

{mode_instructions}

## Cluster signature

seed: {seed}  ({seed_title})
seed_summary: {seed_summary}
size: {size} notes (depth {depth})
contradicts_ratio: {contradicts_ratio}
edge_distribution: {edge_distribution}

### Load-bearing nodes (high in-degree, low pressure-testing — primary fracture targets)
{load_bearing_block}

### Frontier nodes (terminal — no outgoing builds-on inside cluster — primary extension targets)
{frontier_block}

### Thematic vocabulary (cluster's existing concept space — do not duplicate)
{vocab_block}

## Task
"""


def _format_block(items: list[dict[str, Any]], fields: list[str]) -> str:
    if not items:
        return "(none)"
    lines: list[str] = []
    for it in items:
        bits = []
        for f in fields:
            v = it.get(f)
            if v is not None:
                bits.append(f"{f}={v}")
        lines.append("  - " + ", ".join(bits))
    return "\n".join(lines)


def _format_vocab(vocab: list[tuple[str, int] | list]) -> str:
    if not vocab:
        return "(none)"
    return ", ".join(f"{w}({c})" for w, c in vocab)


def build_synthesis_prompt(
    signature: dict[str, Any],
    mode: str,
    k: int = 5,
) -> str:
    """Render a Claude-ready prompt that consumes the cluster signature and
    instructs the model to propose k research domains in the requested mode.

    Pure string templating — no side effects, no LLM call. The caller (slash
    command) feeds this prompt to Claude.
    """
    if mode not in MODES:
        raise ValueError(f"unknown mode '{mode}' — pick one of {MODES}")

    header = _HEADER.format(
        mode=mode,
        mode_instructions=_MODE_INSTRUCTIONS[mode],
        seed=signature.get("seed", "?"),
        seed_title=signature.get("seed_title", "?"),
        seed_summary=signature.get("seed_summary", "?"),
        size=signature.get("size", 0),
        depth=signature.get("depth", 0),
        contradicts_ratio=signature.get("contradicts_ratio", 0.0),
        edge_distribution=signature.get("edge_distribution", {}),
        load_bearing_block=_format_block(
            signature.get("load_bearing", []),
            ["note_id", "in_degree", "contradicts_in", "unchallenged_load_score"],
        ),
        frontier_block=_format_block(
            signature.get("frontier", []),
            ["note_id", "title"],
        ),
        vocab_block=_format_vocab(signature.get("thematic_vocabulary", [])),
    )

    task = _PER_DOMAIN_TEMPLATE.format(k=k, mode=mode)
    return header + task
