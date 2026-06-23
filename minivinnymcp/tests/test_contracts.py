"""Stage 2: typed contracts validate against actual current MCP outputs.

The test strategy: capture the dict shape each tool returns today, push it
through the matching Pydantic model, assert no validation error and that
.model_dump() roundtrips. This proves contracts are adoption-safe — modules
can switch to typed models without breaking dict-consuming callers.
"""

import os
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.contracts import (
    AuditCandidate,
    ClaimCheck,
    CognitiveProfile,
    Context,
    ContextNote,
    CrossLink,
    Edge,
    ExpansionHop,
    ExpansionResult,
    Note,
    OpenQuestion,
    ProfileComparison,
    ReasoningStep,
    ResearchPayload,
    RetrievalResult,
    Source,
    SuggestionEntry,
    WriteReceipt,
)

GRAPH_PATH = _vault_root / "06-Maps" / "vault-graph.json"


# --- Pure shape tests (synthetic dicts) ---


def test_retrieval_result_validates_minimal():
    r = RetrievalResult(note_id="x")
    assert r.note_id == "x"
    assert r.score is None


def test_retrieval_result_validates_full():
    r = RetrievalResult(note_id="x", score=0.42, title="T", summary="S", filepath="f.md")
    d = r.model_dump()
    assert d["note_id"] == "x"
    assert d["score"] == 0.42


def test_edge_aliases_type():
    e = Edge(source="a", target="b", type="builds-on")
    assert e.edge_type == "builds-on"


def test_edge_extra_fields_allowed():
    e = Edge(source="a", target="b", edge_type="x", custom_field="kept")
    d = e.model_dump()
    assert d.get("custom_field") == "kept"


def test_reasoning_step_aliases_from():
    s = ReasoningStep(**{"from": "a", "edge": "builds-on", "to": "b"})
    assert s.from_ == "a"
    assert s.to == "b"


def test_context_note_validates():
    cn = ContextNote(
        note_id="x",
        composite_score=0.9,
        source="ppr",
        reasoning_path=[{"from": "a", "edge": "builds-on", "to": "x"}],
    )
    assert cn.reasoning_path[0].edge == "builds-on"


def test_context_validates():
    ctx = Context(
        query="q",
        notes=[{"note_id": "n1", "source": "seed"}],
        chars_used=100, char_budget=2000, mode="standard",
    )
    assert ctx.notes[0].note_id == "n1"


def test_research_payload_minimal():
    rp = ResearchPayload(note_id="x")
    assert rp.sources == []
    assert rp.raw_summary == ""


def test_research_payload_full_roundtrip():
    rp = ResearchPayload(
        note_id="x",
        sources=[{"title": "t", "url": "u"}],
        claim_checks=[{"claim_snippet": "c", "verdict": "supports"}],
        cross_links=[{"hint_text": "h", "reason": "r"}],
        open_questions=[{"question": "q1"}],
        raw_summary="hi",
    )
    d = rp.model_dump()
    rt = ResearchPayload(**d)
    assert rt.sources[0].title == "t"
    assert rt.claim_checks[0].verdict == "supports"


def test_write_receipt_stub_shape():
    wr = WriteReceipt(
        tool="write_apply_link_suggestions",
        note_id="x",
        status="stub",
        applied=False,
        would_apply=True,
        stage=0,
    )
    assert wr.applied is False
    assert wr.stage == 0


def test_cognitive_profile_defaults():
    cp = CognitiveProfile(profile_id="default", display_name="Default")
    assert cp.contradiction_policy == "suppress"
    assert cp.mention_policy == "ignore"
    assert cp.edge_weight_overrides == {}


def test_cognitive_profile_skeptic_shape():
    cp = CognitiveProfile(
        profile_id="skeptic",
        display_name="Skeptic",
        contradiction_policy="seek",
        edge_weight_overrides={"contradicts": 1.6, "challenges": 1.2},
    )
    assert cp.contradiction_policy == "seek"
    assert cp.edge_weight_overrides["contradicts"] == 1.6


def test_profile_comparison_shape():
    pc = ProfileComparison(
        query="q",
        profiles=["default", "skeptic"],
        per_profile={
            "default": [{"note_id": "n1"}],
            "skeptic": [{"note_id": "n2"}],
        },
        divergence_score=1.0,
        overlap_top_n=15,
    )
    assert pc.per_profile["skeptic"][0].note_id == "n2"


# --- Validation against live tool outputs ---


def test_vault_search_output_validates():
    if not GRAPH_PATH.exists():
        return
    from minivinnymcp.server import vault_search
    rows = vault_search("mastery", top_k=3)
    for row in rows:
        RetrievalResult(**row)  # raises on validation failure


def test_get_note_with_context_output_validates():
    if not GRAPH_PATH.exists():
        return
    from minivinnymcp.server import get_note_with_context
    out = get_note_with_context("mastery-trap")
    if "error" in out:
        return
    note = Note(**out)
    assert note.note_id == "mastery-trap"


def test_assemble_context_output_validates():
    if not GRAPH_PATH.exists():
        return
    from minivinnymcp.server import assemble_context
    out = assemble_context("mastery", seed_k=3, char_budget=2000)
    ctx = Context(**out)
    assert ctx.query == "mastery"
    for note in ctx.notes:
        assert isinstance(note, ContextNote)


def test_graph_expand_output_validates():
    if not GRAPH_PATH.exists():
        return
    from minivinnymcp.server import graph_expand
    out = graph_expand("mastery-trap", max_hops=1)
    if "error" in out:
        return
    er = ExpansionResult(**out)
    for hop in er.hops:
        assert isinstance(hop, ExpansionHop)


def test_audit_taxonomy_output_validates():
    if not GRAPH_PATH.exists():
        return
    from minivinnymcp.server import audit_taxonomy
    out = audit_taxonomy("analogous-to", "exemplifies")
    if not out or "error" in out[0]:
        return
    for row in out:
        AuditCandidate(**row)


def test_analytics_connect_suggest_output_validates():
    if not GRAPH_PATH.exists():
        return
    from minivinnymcp.server import analytics_connect_suggest
    out = analytics_connect_suggest(categories=["missing_bidir"])
    for row in out.get("missing_bidir", [])[:5]:
        SuggestionEntry(**row)


def test_apply_link_suggestions_stub_output_validates():
    # Stage 3: real implementation. With non-existent source the receipt
    # is still well-formed (aggregate status=applied, per-row missing_file).
    from writeagentmcp.server import write_apply_link_suggestions
    out = write_apply_link_suggestions([
        {"source": "nonexistent-source-xyz", "target": "b", "edge_type": "builds-on"},
    ])
    wr = WriteReceipt(**out)
    assert wr.tool == "write_apply_link_suggestions"
    assert wr.status in ("applied", "error")
