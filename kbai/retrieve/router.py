"""Query router — classify a query so the pipeline can skip the graph walk for
simple fact lookups.

Research (arXiv 2502.11371 etc.): plain dense RAG matches or beats GraphRAG on
single-hop FACT retrieval, where the typed-graph walk only adds connected-but-
redundant notes. So short, single-entity lookups take a dense-only fast path;
everything else keeps the full pipeline. Reasoning is the SAFE DEFAULT — the
classifier only routes to 'fact' when it's clearly a simple lookup.
"""

from __future__ import annotations

import re

# Tokens that signal a reasoning/relational query (→ full graph walk). 'and'
# is included: two concepts joined is a relationship, not a single-entity lookup.
_REASONING = re.compile(
    r"\b(vs|versus|difference|differences|between|compare|comparison|contrast|"
    r"relationship|relate|related|connect|connection|how|why|tradeoff|trade-off|"
    r"impact|affect|influence|cause|because|and|or)\b",
    re.IGNORECASE,
)


# An EXPLICIT lookup lead. Length alone is a bad signal in a concept vault — a
# short query like "governance capital" is a CONCEPT (wants graph expansion),
# not a fact lookup. Only these leads, with no relational signal, take the fast path.
_FACT_LEAD = re.compile(
    r"^(what\s+(is|are|was|were)|define|definition\s+of|who\s+(is|was|were)|"
    r"when\s+(did|was|is)|where\s+(is|was))\b",
    re.IGNORECASE,
)


def classify_query(query: str) -> str:
    """Return 'fact' (dense-only fast path) or 'reasoning' (full graph walk).

    'reasoning' is the safe default — including for short *concept* queries, which
    want graph expansion, not a bare lookup. Only an explicit lookup lead
    ('what is X', 'define X', 'who is X') with no relational signal routes to fact.
    """
    q = (query or "").strip()
    if not q:
        return "reasoning"
    if _REASONING.search(q):
        return "reasoning"
    return "fact" if _FACT_LEAD.match(q) else "reasoning"
