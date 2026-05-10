"""Stage 5.5 partial: cognitive routing registry, applier, and read-side tools.

Verifies:
  - Each shipped YAML profile loads cleanly into CognitiveProfile.
  - Registry list/load are deterministic.
  - Applier produces the expected effective config for default (no-op),
    skeptic (boosts contradicts, allows them in walk), operator (boosts
    operationalises, prefers concrete), builder (boosts builds-on, deep paths).
  - MCP tools registered and callable.
"""

import os
import sys
from pathlib import Path

import pytest

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.cognitive_routing import (
    apply_profile,
    list_profile_ids,
    list_profiles,
    load_profile,
)
from kbai.contracts import CognitiveProfile


# --- registry ---


def test_registry_contains_v1_profiles():
    ids = set(list_profile_ids())
    assert {"default", "skeptic", "operator", "builder"} <= ids


def test_each_profile_loads_into_typed_model():
    profiles = list_profiles()
    assert len(profiles) >= 4
    for p in profiles:
        assert isinstance(p, CognitiveProfile)
        assert p.profile_id
        assert p.display_name
        assert p.schema_version == 1


def test_load_profile_unknown_raises():
    with pytest.raises(FileNotFoundError):
        load_profile("does-not-exist")


def test_no_person_named_profile_in_v1():
    """Decision #11: person-named profiles must not ship in v1.
    They become earnable in Stage 8 calibration."""
    forbidden = {"vinay", "girlfriend", "boyfriend", "mom", "dad"}
    assert forbidden.isdisjoint(set(list_profile_ids())), \
        "Person-named profiles must not exist in v1 — see Decision #11 in refactor-plan.md"


# --- applier shape ---


def _base_weights():
    return {
        "builds-on": 1.5,
        "builds-toward": 1.5,
        "contradicts": 1.2,
        "analogous-to": 1.3,
        "exemplifies": 0.85,
        "challenges": 0.80,
        "operationalises": 0.85,
        "referenced-in": 0.8,
        "untyped": 0.6,
        "mentioned": 0.3,
    }


def test_default_profile_is_noop_on_weights():
    p = load_profile("default")
    out = apply_profile(p, _base_weights())
    # Default has no weight overrides → effective weights == base
    assert out["effective_weights"] == _base_weights()


def test_default_profile_excludes_contradicts_and_mentioned():
    p = load_profile("default")
    out = apply_profile(p, _base_weights())
    assert "contradicts" in out["effective_exclude_types"]
    assert "mentioned" in out["effective_exclude_types"]


def test_skeptic_admits_contradicts_into_walk():
    p = load_profile("skeptic")
    out = apply_profile(p, _base_weights())
    assert "contradicts" not in out["effective_exclude_types"]
    # And boosts it
    assert out["effective_weights"]["contradicts"] > _base_weights()["contradicts"]


def test_skeptic_boosts_challenges():
    p = load_profile("skeptic")
    out = apply_profile(p, _base_weights())
    assert out["effective_weights"]["challenges"] > _base_weights()["challenges"]


def test_operator_boosts_operationalises_and_exemplifies():
    p = load_profile("operator")
    out = apply_profile(p, _base_weights())
    assert out["effective_weights"]["operationalises"] > _base_weights()["operationalises"]
    assert out["effective_weights"]["exemplifies"] > _base_weights()["exemplifies"]
    assert out["path_length_hint"] == "short"
    assert out["abstraction_hint"] == "concrete"


def test_builder_boosts_builds_on_and_prefers_deep_paths():
    p = load_profile("builder")
    out = apply_profile(p, _base_weights())
    assert out["effective_weights"]["builds-on"] > _base_weights()["builds-on"]
    assert out["effective_weights"]["builds-toward"] > _base_weights()["builds-toward"]
    assert out["path_length_hint"] == "deep"


def test_applier_respects_base_excludes():
    """Caller-supplied base excludes (e.g. mode-level) must not be dropped
    by the applier — profile policy is additive."""
    p = load_profile("skeptic")
    out = apply_profile(p, _base_weights(), base_exclude_types={"untyped"})
    assert "untyped" in out["effective_exclude_types"]
    # Skeptic still admits contradicts despite base excludes
    assert "contradicts" not in out["effective_exclude_types"]


def test_applier_returns_all_documented_keys():
    p = load_profile("default")
    out = apply_profile(p, _base_weights())
    expected = {
        "profile_id",
        "effective_weights",
        "effective_exclude_types",
        "path_length_hint",
        "abstraction_hint",
        "restart_bias_tags",
        "confidence_threshold",
    }
    assert expected <= set(out.keys())


# --- MCP tools ---


def test_cognition_tools_registered():
    from minivinnymcp.server import app
    tm = getattr(app, "_tool_manager", None)
    if tm is None:
        return
    names = set(tm._tools.keys())
    assert {"cognition_list_profiles", "cognition_get_profile"} <= names


def test_cognition_list_profiles_returns_dicts():
    from minivinnymcp.server import cognition_list_profiles
    out = cognition_list_profiles()
    assert isinstance(out, list)
    assert len(out) >= 4
    for entry in out:
        assert "profile_id" in entry
        assert "edge_weight_overrides" in entry


def test_cognition_get_profile_known_id():
    from minivinnymcp.server import cognition_get_profile
    out = cognition_get_profile("skeptic")
    assert out["profile_id"] == "skeptic"
    assert out["contradiction_policy"] == "seek"


def test_cognition_get_profile_unknown_id_returns_error():
    from minivinnymcp.server import cognition_get_profile
    out = cognition_get_profile("not-a-profile")
    assert "error" in out
