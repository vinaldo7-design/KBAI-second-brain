"""Stage 0 item 2: assert vault_taxonomy.yaml and vault_graph.TYPED_LINK_SECTIONS
do not drift. The yaml is canonical; the dict is the fallback. Both must agree
on the section_heading → edge_type mapping for every type that has a heading."""

import os
import sys
from pathlib import Path

import yaml

_vault_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(_vault_root))

from vault_graph import TYPED_LINK_SECTIONS, UNTYPED_LINK_SECTION_NAMES

TAXONOMY_PATH = _vault_root / "vault_taxonomy.yaml"


def _load_yaml() -> dict:
    with open(TAXONOMY_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def test_every_yaml_typed_section_in_fallback():
    """Every edge type in yaml with a section_heading must appear in the fallback."""
    data = _load_yaml()
    edge_types = data.get("edge_types", {})
    yaml_typed = {
        meta["section_heading"]: et
        for et, meta in edge_types.items()
        if meta.get("section_heading")
    }
    missing = {h: t for h, t in yaml_typed.items() if h not in TYPED_LINK_SECTIONS}
    assert not missing, f"Yaml has typed sections not in fallback dict: {missing}"


def test_fallback_subset_of_yaml():
    """Fallback dict must not have entries the yaml does not declare."""
    data = _load_yaml()
    edge_types = data.get("edge_types", {})
    yaml_headings = {
        meta["section_heading"]
        for meta in edge_types.values()
        if meta.get("section_heading")
    }
    extras = set(TYPED_LINK_SECTIONS.keys()) - yaml_headings
    assert not extras, f"Fallback dict has entries not in yaml: {extras}"


def test_challenges_present_in_fallback():
    """Regression guard for the original Stage 0 drift."""
    assert "challenges" in TYPED_LINK_SECTIONS
    assert TYPED_LINK_SECTIONS["challenges"] == "challenges"


def test_yaml_untyped_sections_align_with_fallback():
    data = _load_yaml()
    yaml_untyped = set(data.get("untyped_section_names", []))
    if yaml_untyped:
        missing = yaml_untyped - UNTYPED_LINK_SECTION_NAMES
        assert not missing, f"Yaml untyped names not in fallback: {missing}"
