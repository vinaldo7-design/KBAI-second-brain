"""Phase 3: section_patcher derives headings from vault_taxonomy.yaml.

Asserts that every yaml edge_type with a section_heading resolves through
patch_section — no "no_section" for canonical types. Kills the silent
`referenced-in` bug specifically.
"""

import os
import sys
from pathlib import Path

import yaml

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.storage.section_patcher import EDGE_HEADING, patch_section


_TAXONOMY_PATH = _vault_root / "vault_taxonomy.yaml"


def _yaml_edge_types_with_headings() -> list[tuple[str, str]]:
    """[(edge_type, section_heading), ...] from vault_taxonomy.yaml."""
    with open(_TAXONOMY_PATH, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    out = []
    for et, meta in (data.get("edge_types") or {}).items():
        sh = (meta or {}).get("section_heading")
        if sh:
            out.append((et, sh))
    return out


def test_edge_heading_map_keys_match_yaml():
    """Every yaml edge_type with section_heading must appear in EDGE_HEADING."""
    yaml_types = {et for et, _ in _yaml_edge_types_with_headings()}
    assert yaml_types == set(EDGE_HEADING.keys()), (
        f"drift: yaml has {yaml_types}, EDGE_HEADING has {set(EDGE_HEADING.keys())}"
    )


def test_every_yaml_edge_type_resolves_to_section():
    """For each yaml edge_type, build a note containing the yaml's heading text
    (uppercased first letter) and confirm patch_section finds it."""
    for edge_type, yaml_heading in _yaml_edge_types_with_headings():
        display = yaml_heading[0].upper() + yaml_heading[1:]
        body = f"# Note\n\n### {display}\n- \n\n## Status Log\n"
        new_text, status = patch_section(body, edge_type, "target-note")
        assert status == "patched", (
            f"edge_type={edge_type!r} (heading {display!r}) returned {status!r}"
        )
        assert "[[target-note]]" in new_text


def test_referenced_in_specifically_resolves():
    """The Phase 3 bug fix: patch_section was hardcoded to 'referenced-in-maps'
    while yaml + parser use 'referenced-in'. Verify the yaml key resolves."""
    body = "# Note\n\n### Referenced in Maps\n- \n"
    new_text, status = patch_section(body, "referenced-in", "some-map")
    assert status == "patched"
    assert "[[some-map]]" in new_text


def test_case_insensitive_heading_match():
    """Real-vault notes vary heading casing (sentence-case vs title-case).
    Match must be case-insensitive."""
    for heading_variant in (
        "### Referenced in Maps",
        "### Referenced in maps",
        "### referenced in maps",
        "### REFERENCED IN MAPS",
    ):
        body = f"# Note\n\n{heading_variant}\n- \n"
        _, status = patch_section(body, "referenced-in", "x")
        assert status == "patched", f"failed on heading variant: {heading_variant!r}"


def test_old_buggy_key_no_longer_resolves():
    """'referenced-in-maps' is not a yaml edge_type — passing it must return
    no_section (and would have, even pre-Phase 3, since no edge in the
    taxonomy uses that key)."""
    body = "# Note\n\n### Referenced in Maps\n- \n"
    _, status = patch_section(body, "referenced-in-maps", "x")
    assert status == "no_section"


def test_unknown_edge_type_returns_no_section():
    body = "# Note\n\n### Builds on\n- \n"
    _, status = patch_section(body, "not-a-real-type", "x")
    assert status == "no_section"


def test_untyped_and_mentioned_have_no_section():
    """yaml defines section_heading: null for untyped and mentioned; both must
    return no_section so callers can't accidentally write into a structural
    section that shouldn't exist."""
    body = "# Note\n\n### Builds on\n- \n"
    for et in ("untyped", "mentioned"):
        _, status = patch_section(body, et, "x")
        assert status == "no_section", f"{et!r} should resolve to no_section"
