import json
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import patch

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
os.environ.setdefault("PERPLEXITY_API_KEY", "test-key")
sys.path.insert(0, str(_vault_root))

from perplexitymcp.server import (
    _cluster_expand,
    _extract_json,
    _format_research_section,
    _match_vault_note,
    _normalize,
    apply_research,
    research_cluster,
    research_note,
    research_verify_claim,
)


# --- _extract_json ---

def test_extract_json_plain():
    raw = '{"sources": [], "claim_checks": [], "cross_links": [], "open_questions": [], "raw_summary": "x"}'
    parsed = _extract_json(raw)
    assert parsed["raw_summary"] == "x"


def test_extract_json_fenced():
    raw = '```json\n{"sources": [{"title": "T", "url": "u", "summary": "s", "published": null}]}\n```'
    parsed = _extract_json(raw)
    assert parsed["sources"][0]["title"] == "T"


def test_extract_json_with_prose():
    raw = 'Here is the result:\n\n{"raw_summary": "hello"}\n\nLet me know if you need more.'
    parsed = _extract_json(raw)
    assert parsed["raw_summary"] == "hello"


def test_extract_json_fills_missing_keys():
    raw = '{"raw_summary": "only this"}'
    parsed = _extract_json(raw)
    assert parsed["sources"] == []
    assert parsed["claim_checks"] == []
    assert parsed["cross_links"] == []


def test_extract_json_invalid_raises():
    import pytest
    with pytest.raises(RuntimeError):
        _extract_json("no json here at all")


# --- _normalize and _match_vault_note ---

def test_normalize():
    assert _normalize("Causal Inference!") == "causal-inference"
    assert _normalize("DAG — Directed Acyclic Graph") == "dag-directed-acyclic-graph"


def test_match_vault_note_by_id():
    graph = {"nodes": [{"id": "mastery-trap", "title": "Mastery Trap"}]}
    assert _match_vault_note("mastery-trap", graph) == "mastery-trap"


def test_match_vault_note_by_title():
    graph = {"nodes": [{"id": "mastery-trap", "title": "Mastery Trap"}]}
    assert _match_vault_note("Mastery Trap", graph) == "mastery-trap"


def test_match_vault_note_fuzzy_substring():
    graph = {"nodes": [{"id": "causal-inference-and-ml", "title": "Causal Inference and ML"}]}
    assert _match_vault_note("causal inference", graph) == "causal-inference-and-ml"


def test_match_vault_note_no_match():
    graph = {"nodes": [{"id": "x", "title": "X"}]}
    assert _match_vault_note("totally unrelated", graph) is None


def test_match_vault_note_empty_graph():
    assert _match_vault_note("anything", None) is None


# --- _format_research_section ---

def test_format_section_full():
    payload = {
        "sources": [{"title": "T", "url": "https://x.com", "summary": "s", "published": "2024"}],
        "claim_checks": [{
            "claim_snippet": "X causes Y",
            "verdict": "supports",
            "evidence": [{"url": "https://e.com", "note": "study A"}],
        }],
        "cross_links": [{"hint_text": "Z", "vault_note_id": "z-note", "reason": "related"}],
        "open_questions": [{"question": "What about W?", "reason": "missing"}],
        "raw_summary": "summary text",
    }
    section = _format_research_section(payload, include_raw_summary=True)
    assert "## External research (Perplexity" in section
    assert "[T](https://x.com)" in section
    assert "**supports**" in section
    assert "[[z-note]]" in section
    assert "What about W?" in section
    assert "summary text" in section


def test_format_section_excludes_raw_when_disabled():
    payload = {"sources": [], "claim_checks": [], "cross_links": [], "open_questions": [], "raw_summary": "secret"}
    section = _format_research_section(payload, include_raw_summary=False)
    assert "secret" not in section


def test_format_section_no_vault_match_marked():
    payload = {
        "sources": [], "claim_checks": [],
        "cross_links": [{"hint_text": "unmatched", "reason": "r"}],
        "open_questions": [], "raw_summary": "",
    }
    section = _format_research_section(payload, include_raw_summary=False)
    assert "no vault match" in section


# --- research_note (mocked API) ---

def _mock_response(payload: dict, status: int = 200):
    class MockResp:
        status_code = status
        text = json.dumps(payload) if status != 200 else ""
        def json(self):
            return payload
    return MockResp()


def _fake_api_response():
    return {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "sources": [{"title": "S1", "url": "u1", "summary": "sum1", "published": "2025"}],
                    "claim_checks": [],
                    "cross_links": [{"hint_text": "Mastery Trap", "reason": "directly related"}],
                    "open_questions": [],
                    "raw_summary": "raw",
                })
            }
        }]
    }


def test_research_note_unknown_returns_error():
    result = research_note("nonexistent-note-xyz")
    assert "error" in result


def test_research_note_with_mocked_api(tmp_path):
    note_file = _vault_root / "00-Captures" / "test-perplexity-research.md"
    note_file.write_text("# Test Note\n\nSome content.\n", encoding="utf-8")
    try:
        with patch("perplexitymcp.server.requests.post", return_value=_mock_response(_fake_api_response())):
            result = research_note("test-perplexity-research")
        assert "error" not in result
        assert result["note_id"] == "test-perplexity-research"
        assert result["sources"][0]["title"] == "S1"
        assert "researched_at" in result
    finally:
        note_file.unlink(missing_ok=True)


def test_research_note_augments_cross_links_with_vault_match(tmp_path):
    note_file = _vault_root / "00-Captures" / "test-perplexity-augment.md"
    note_file.write_text("# Test\n", encoding="utf-8")
    try:
        with patch("perplexitymcp.server.requests.post", return_value=_mock_response(_fake_api_response())):
            result = research_note("test-perplexity-augment")
        # 'Mastery Trap' should match the existing mastery-trap note in the vault
        cross = result["cross_links"]
        if cross and (_vault_root / "06-Maps" / "vault-graph.json").exists():
            assert any(cl.get("vault_note_id") == "mastery-trap" for cl in cross)
    finally:
        note_file.unlink(missing_ok=True)


def test_research_note_handles_api_error():
    note_file = _vault_root / "00-Captures" / "test-perplexity-err.md"
    note_file.write_text("# x\n", encoding="utf-8")
    try:
        with patch("perplexitymcp.server.requests.post", return_value=_mock_response({}, status=500)):
            result = research_note("test-perplexity-err")
        assert "error" in result
    finally:
        note_file.unlink(missing_ok=True)


# --- apply_research ---

def test_apply_research_appends_section():
    note_file = _vault_root / "00-Captures" / "test-apply.md"
    original = "# Original\n\nMy own prose.\n"
    note_file.write_text(original, encoding="utf-8")
    try:
        result = apply_research(
            note_id="test-apply",
            sources=[{"title": "T", "url": "u", "summary": "s", "published": None}],
            include_raw_summary=False,
        )
        assert result.get("status") == "appended"
        new_content = note_file.read_text(encoding="utf-8")
        assert "My own prose." in new_content  # original preserved
        assert "## External research (Perplexity" in new_content
        assert "[T](u)" in new_content
    finally:
        note_file.unlink(missing_ok=True)


def test_apply_research_unknown_note_errors():
    result = apply_research(note_id="does-not-exist-xyz")
    assert "error" in result


def test_apply_research_does_not_rewrite_body():
    note_file = _vault_root / "00-Captures" / "test-no-rewrite.md"
    body = "# Sacred Original\n\nLine 1.\nLine 2.\nLine 3.\n"
    note_file.write_text(body, encoding="utf-8")
    try:
        apply_research(
            note_id="test-no-rewrite",
            open_questions=[{"question": "Q?", "reason": "r"}],
            include_raw_summary=False,
        )
        new_content = note_file.read_text(encoding="utf-8")
        # Original body must appear verbatim before the section
        idx = new_content.find("## External research")
        assert idx > 0
        prefix = new_content[:idx]
        assert "Line 1." in prefix and "Line 2." in prefix and "Line 3." in prefix
    finally:
        note_file.unlink(missing_ok=True)


# --- research_cluster ---


def _fake_graph_for_cluster():
    return {
        "nodes": [
            {"id": "map-a"}, {"id": "note-b"}, {"id": "note-c"}, {"id": "note-d"},
        ],
        "edges": [
            {"source": "map-a", "target": "note-b", "type": "builds-on", "target_exists": True},
            {"source": "map-a", "target": "note-c", "type": "exemplifies", "target_exists": True},
            {"source": "note-c", "target": "note-d", "type": "analogous-to", "target_exists": True},
        ],
    }


def test_cluster_expand_one_hop():
    with patch("perplexitymcp.server._load_graph", return_value=_fake_graph_for_cluster()):
        result = _cluster_expand("map-a", cluster_hops=1)
    assert set(result) == {"note-b", "note-c"}
    assert "map-a" not in result


def test_cluster_expand_two_hops():
    with patch("perplexitymcp.server._load_graph", return_value=_fake_graph_for_cluster()):
        result = _cluster_expand("map-a", cluster_hops=2)
    assert set(result) == {"note-b", "note-c", "note-d"}


def test_cluster_expand_empty_graph():
    with patch("perplexitymcp.server._load_graph", return_value=None):
        assert _cluster_expand("map-a", cluster_hops=1) == []


def test_research_cluster_happy_path(tmp_path):
    note_a = _vault_root / "00-Captures" / "test-cluster-map.md"
    note_b = _vault_root / "00-Captures" / "test-cluster-nb.md"
    note_a.write_text("# Cluster root\n", encoding="utf-8")
    note_b.write_text("# Neighbour B\n", encoding="utf-8")
    try:
        with patch("perplexitymcp.server._cluster_expand", return_value=["test-cluster-nb"]), \
             patch("perplexitymcp.server.requests.post",
                   return_value=_mock_response(_fake_api_response())):
            result = research_cluster("test-cluster-map", cluster_hops=1)
        assert "error" not in result
        assert result["note_id"] == "test-cluster-map"
        assert "cluster_notes" in result
        assert "test-cluster-map" in result["cluster_notes"]
    finally:
        note_a.unlink(missing_ok=True)
        note_b.unlink(missing_ok=True)


def test_research_cluster_no_graph_returns_error():
    with patch("perplexitymcp.server._cluster_expand", return_value=[]):
        result = research_cluster("nonexistent-map-xyz", cluster_hops=1)
    assert "error" in result


def test_research_cluster_missing_api_key(tmp_path):
    note_a = _vault_root / "00-Captures" / "test-cluster-nokey.md"
    note_a.write_text("# x\n", encoding="utf-8")
    try:
        saved = os.environ.pop("PERPLEXITY_API_KEY", None)
        with patch("perplexitymcp.server._cluster_expand", return_value=["test-cluster-nokey"]):
            result = research_cluster("test-cluster-nokey", cluster_hops=1)
        assert "error" in result
    finally:
        if saved:
            os.environ["PERPLEXITY_API_KEY"] = saved
        note_a.unlink(missing_ok=True)


# --- research_verify_claim ---


def _fake_verify_api_response(verdict: str = "supports", confidence: float = 0.9):
    return {
        "choices": [{
            "message": {
                "content": json.dumps({
                    "verdict": verdict,
                    "confidence": confidence,
                    "evidence": [{"url": "https://example.com", "note": "Study confirms."}],
                })
            }
        }]
    }


def test_research_verify_claim_supports():
    with patch("perplexitymcp.server.requests.post",
               return_value=_mock_response(_fake_verify_api_response("supports", 0.85))):
        result = research_verify_claim("Mastery requires 10,000 hours of deliberate practice.")
    assert result["verdict"] == "supports"
    assert 0.0 <= result["confidence"] <= 1.0
    assert isinstance(result["evidence"], list)
    assert result["claim"].startswith("Mastery")


def test_research_verify_claim_invalid_verdict_normalised():
    with patch("perplexitymcp.server.requests.post",
               return_value=_mock_response(_fake_verify_api_response("bogus_verdict", 0.5))):
        result = research_verify_claim("Some claim.")
    assert result["verdict"] == "uncertain"


def test_research_verify_claim_missing_api_key():
    saved = os.environ.pop("PERPLEXITY_API_KEY", None)
    try:
        result = research_verify_claim("Any claim.")
    finally:
        if saved:
            os.environ["PERPLEXITY_API_KEY"] = saved
    assert "error" in result
