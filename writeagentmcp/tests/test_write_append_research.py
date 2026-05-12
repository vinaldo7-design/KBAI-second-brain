"""Tests for kbai/storage/research_appender.py (write_append_research_section)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from kbai.storage.research_appender import append_research_section


def _vault(tmp_path: Path) -> Path:
    (tmp_path / "06-Maps").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _make_note(vault: Path, folder: str, note_id: str, content: str = "# Test Note\n\nBody text.") -> Path:
    folder_path = vault / folder
    folder_path.mkdir(parents=True, exist_ok=True)
    note = folder_path / f"{note_id}.md"
    note.write_text(content, encoding="utf-8")
    return note


_PAYLOAD = {
    "note_id": "test-note",
    "sources": [{"title": "LessWrong post", "url": "https://lesswrong.com/foo"}],
    "claim_checks": [{"claim_snippet": "The sky is blue", "verdict": "supports"}],
    "cross_links": [{"vault_note_id": "related-note", "reason": "closely related theme"}],
    "open_questions": [{"question": "What causes this effect?"}],
    "raw_summary": "Brief synthesis of external findings.",
}


def test_happy_path_section_appended(tmp_path):
    vault = _vault(tmp_path)
    note = _make_note(vault, "01-Ideas", "test-note")

    receipt = append_research_section(vault, "test-note", _PAYLOAD)

    assert receipt.status == "applied"
    assert receipt.applied is True
    content = note.read_text(encoding="utf-8")
    assert "## External research (Perplexity," in content
    assert "### Sources" in content
    assert "LessWrong post" in content
    assert "### Claim checks" in content
    assert "[supports] The sky is blue" in content
    assert "### Cross-links" in content
    assert "[[related-note]]" in content
    assert "closely related theme" in content
    assert "### Open questions" in content
    assert "What causes this effect?" in content
    assert "### Summary" in content
    assert "Brief synthesis of external findings." in content


def test_idempotent_same_day(tmp_path):
    vault = _vault(tmp_path)
    note = _make_note(vault, "01-Ideas", "test-note")

    append_research_section(vault, "test-note", _PAYLOAD)
    after_first = note.read_bytes()

    receipt2 = append_research_section(vault, "test-note", _PAYLOAD)

    assert receipt2.status == "already_present"
    assert receipt2.applied is False
    assert note.read_bytes() == after_first


def test_note_not_found_returns_error(tmp_path):
    vault = _vault(tmp_path)

    receipt = append_research_section(vault, "nonexistent-note", _PAYLOAD)

    assert receipt.status == "error"
    assert receipt.applied is False


def test_dryrun_file_unchanged(tmp_path):
    vault = _vault(tmp_path)
    note = _make_note(vault, "01-Ideas", "test-note")
    original = note.read_bytes()

    receipt = append_research_section(vault, "test-note", _PAYLOAD, dryrun=True)

    assert receipt.status in ("dryrun", "dry_run")
    assert receipt.applied is False
    assert note.read_bytes() == original


def test_hash_changes_on_write(tmp_path):
    vault = _vault(tmp_path)
    _make_note(vault, "01-Ideas", "test-note")

    receipt = append_research_section(vault, "test-note", _PAYLOAD)

    assert receipt.status == "applied"
    assert receipt.hash_before is not None
    assert receipt.hash_after is not None
    assert receipt.hash_before != receipt.hash_after
