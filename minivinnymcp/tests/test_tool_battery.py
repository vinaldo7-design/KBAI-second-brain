"""Task 1: deferred-tool discovery probe battery.

Drift-detector pattern (the reusable artefact of the drift-elimination arc):
assert the runtime-derived set equals its declared source set. Here the
runtime-derived set is what the probe battery *surfaces*; the source set is
``TOOL_REGISTRY``.

The harness ``tool_search`` is not available inside pytest, so these tests model
it with ``simulate_tool_search`` — a deterministic top-k keyword matcher over a
realistic deferred-tool universe (every relevant MCP server's tools plus decoy
tools from other connected servers). The simulator is a faithful, general model
of keyword matching, not reverse-engineered to the battery: a registry tool only
surfaces if a probe's keywords genuinely rank it into the top-k against the
decoys. The production guarantee is the same battery run via the real
``tool_search`` at session start (see ``~/.claude/commands/capture.md`` Step 0).
"""

import os
import re
import sys
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

from kbai.tool_battery import (  # noqa: E402
    DEFAULT_TOP_K,
    FAMILIES,
    PROBE_BATTERY,
    TOOL_REGISTRY,
    all_registry_tools,
    surface_tools,
)

# --- a realistic deferred-tool universe (the haystack) -----------------------
# Every tool of the three servers the capture/synthesis paths use, plus decoy
# tools from other connected servers so single-keyword families (read, search,
# create) face genuine collisions — exactly the condition that makes a single
# probe unsafe to reason from.

_OBSIDIAN = [
    "mcp__obsidian__obsidian_append_content",
    "mcp__obsidian__obsidian_batch_get_file_contents",
    "mcp__obsidian__obsidian_complex_search",
    "mcp__obsidian__obsidian_delete_file",
    "mcp__obsidian__obsidian_get_file_contents",
    "mcp__obsidian__obsidian_get_periodic_note",
    "mcp__obsidian__obsidian_get_recent_changes",
    "mcp__obsidian__obsidian_get_recent_periodic_notes",
    "mcp__obsidian__obsidian_list_files_in_dir",
    "mcp__obsidian__obsidian_list_files_in_vault",
    "mcp__obsidian__obsidian_patch_content",
    "mcp__obsidian__obsidian_simple_search",
]

_MINI_VINNY = [
    "mcp__mini-vinny__analytics_connect_suggest",
    "mcp__mini-vinny__assemble_context",
    "mcp__mini-vinny__audit_taxonomy",
    "mcp__mini-vinny__cognition_compare_profiles",
    "mcp__mini-vinny__cognition_get_profile",
    "mcp__mini-vinny__cognition_list_profiles",
    "mcp__mini-vinny__cognition_retrieve_as",
    "mcp__mini-vinny__council_retrieve",
    "mcp__mini-vinny__get_note_with_context",
    "mcp__mini-vinny__graph_expand",
    "mcp__mini-vinny__imagine",
    "mcp__mini-vinny__notes_get_with_context",
    "mcp__mini-vinny__recent_notes",
    "mcp__mini-vinny__retrieve_assemble",
    "mcp__mini-vinny__retrieve_search",
    "mcp__mini-vinny__vault_search",
]

_WRITE_AGENT = [
    "mcp__write-agent__write_apply_link_suggestions",
    "mcp__write-agent__write_create_note",
]

# Decoys: representative tools from other connected servers (file connector,
# scheduled tasks, MCP registry). These collide with read/search/create probes.
_DECOYS = [
    "mcp__files__search_files",
    "mcp__files__read_file_content",
    "mcp__files__create_file",
    "mcp__files__copy_file",
    "mcp__files__download_file_content",
    "mcp__files__get_file_metadata",
    "mcp__files__list_recent_files",
    "mcp__scheduled-tasks__create_scheduled_task",
    "mcp__scheduled-tasks__list_scheduled_tasks",
    "mcp__scheduled-tasks__update_scheduled_task",
    "mcp__mcp-registry__search_mcp_registry",
    "mcp__mcp-registry__list_connectors",
    "mcp__mcp-registry__suggest_connectors",
]

UNIVERSE = _OBSIDIAN + _MINI_VINNY + _WRITE_AGENT + _DECOYS


def _tokens(name: str) -> set[str]:
    """Keyword tokens of a tool name — split on any non-alphanumeric, drop the
    'mcp' prefix marker. e.g. mcp__obsidian__obsidian_get_file_contents ->
    {obsidian, get, file, contents}."""
    return {t for t in re.split(r"[^a-z0-9]+", name.lower()) if t and t != "mcp"}


def make_search_fn(universe: list[str]):
    """A deterministic model of the harness tool_search over a fixed universe.

    Scores each tool by keyword overlap with the query, returns the top-k by
    (score desc, name asc), dropping zero-overlap tools. This is a generic
    keyword matcher — it has no knowledge of the battery."""

    def search_fn(query: str, top_k: int) -> list[str]:
        q = {t for t in re.split(r"[^a-z0-9]+", query.lower()) if t}
        scored = [
            (len(q & _tokens(name)), name)
            for name in universe
        ]
        ranked = sorted(
            (s for s in scored if s[0] > 0),
            key=lambda s: (-s[0], s[1]),
        )
        return [name for _, name in ranked[:top_k]]

    return search_fn


# --- structural drift guards -------------------------------------------------

def test_families_registry_and_battery_agree():
    """Every family must have a registry entry and at least one probe; no family
    may exist in one mapping but not the others. Add a family -> add both."""
    assert set(FAMILIES) == set(TOOL_REGISTRY), "FAMILIES drift from TOOL_REGISTRY"
    assert set(FAMILIES) == set(PROBE_BATTERY), "FAMILIES drift from PROBE_BATTERY"
    for family in FAMILIES:
        assert TOOL_REGISTRY[family], f"{family} has no registry tools"
        assert PROBE_BATTERY[family], f"{family} has no probes"


def test_registry_names_well_formed():
    """Every registry tool is a fully-qualified mcp tool on a known server."""
    known_servers = {"obsidian", "mini-vinny", "write-agent"}
    pat = re.compile(r"^mcp__([a-z0-9-]+)__[a-z0-9_]+$")
    for name in all_registry_tools():
        m = pat.match(name)
        assert m, f"malformed tool name: {name}"
        assert m.group(1) in known_servers, f"unknown server in {name}"


def test_registry_subset_of_universe():
    """Sanity: every registry tool actually exists in the deferred-tool universe
    (catches typos / renamed tools in the registry)."""
    missing = all_registry_tools() - set(UNIVERSE)
    assert not missing, f"registry names not present in universe: {missing}"


# --- the drift detector: post-battery set == source set ----------------------

def test_battery_equals_registry_clean():
    """Over a universe that IS exactly the registry, the battery's union must
    equal the registry — the canonical 'runtime-derived set == source set'
    assertion. Completeness AND no-extras, since nothing outside the registry
    exists to surface."""
    search = make_search_fn(sorted(all_registry_tools()))
    surfaced = surface_tools(search, top_k=DEFAULT_TOP_K)
    assert surfaced == all_registry_tools(), (
        f"missing: {all_registry_tools() - surfaced}; "
        f"extra: {surfaced - all_registry_tools()}"
    )


def test_battery_surfaces_full_registry_under_noise():
    """The harder, realistic test: against the full noisy universe (44 tools),
    the battery's union must still surface every registry tool. If a probe's
    keywords let a decoy outrank a needed tool, this fails."""
    search = make_search_fn(UNIVERSE)
    surfaced = surface_tools(search, top_k=DEFAULT_TOP_K)
    missing = all_registry_tools() - surfaced
    assert not missing, f"battery failed to surface under noise: {missing}"


def test_single_probe_is_insufficient():
    """Encodes the observed failure: a single probe surfaces only its top-k and
    cannot reveal the full tool surface. A lone read probe must miss most of the
    registry, and must miss obsidian tools that the full server exposes."""
    search = make_search_fn(UNIVERSE)
    single = set(search(PROBE_BATTERY["read"][0], DEFAULT_TOP_K))

    assert not all_registry_tools().issubset(single), (
        "a single probe surfaced the whole registry — universe too small to "
        "exercise the union guarantee"
    )

    obsidian_in_universe = {n for n in UNIVERSE if "__obsidian__" in n}
    obsidian_surfaced = {n for n in single if "__obsidian__" in n}
    assert obsidian_surfaced < obsidian_in_universe, (
        "a single read probe surfaced every obsidian tool — the multi-probe "
        "battery would be unnecessary"
    )


def test_each_family_probe_set_covers_its_registry():
    """Per-family completeness against the noisy universe — pinpoints which
    family's probes regressed if the union test fails."""
    search = make_search_fn(UNIVERSE)
    for family in FAMILIES:
        surfaced: set[str] = set()
        for query in PROBE_BATTERY[family]:
            surfaced.update(search(query, DEFAULT_TOP_K))
        missing = set(TOOL_REGISTRY[family]) - surfaced
        assert not missing, f"family '{family}' probes miss: {missing}"
