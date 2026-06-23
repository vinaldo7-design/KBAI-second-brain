"""Deferred-tool discovery probe battery (capture-pipeline reliability, Task 1).

Why this exists
---------------
The capture and synthesis paths run inside an agent whose tools are *deferred*
behind a single ``tool_search`` primitive. One probe returns only the top-k
matches for that query's keywords, so an agent that runs one probe and reasons
from the result will conclude tools are missing when they are merely unsurfaced
— and will then invent workarounds for capabilities it actually has.

Observed (2026-06-23 capture session): a read-oriented probe returned 4 obsidian
tools; the obsidian server actually exposes 12. The agent briefly planned a
degraded fallback workflow against tools that were present the whole time.

The fix is a *fixed battery* of probes — at least one query per tool family the
capture/synthesis paths depend on — whose **union** is guaranteed to surface
every tool in the registry. Never reason about tool availability from a single
probe: run the whole battery and take the union.

Source-of-truth contract
-------------------------
- ``TOOL_REGISTRY`` — family -> the fully-qualified tool names that family needs.
  This is the *source set*. The capture path may not assume a tool exists unless
  it is here.
- ``PROBE_BATTERY`` — family -> the fixed ``tool_search`` query strings to run.
- ``surface_tools(search_fn)`` — runs every probe through ``search_fn`` and
  returns the union of surfaced tool names. In production ``search_fn`` is the
  harness ``tool_search``; in tests it is a deterministic simulator of top-k
  keyword matching over a realistic deferred-tool universe.

The drift-detector test (``minivinnymcp/tests/test_tool_battery.py``) asserts the
battery, run over the deferred-tool universe, surfaces exactly the registry — the
same "runtime-derived set == source set" shape used 5x across the
drift-elimination arc. Add a tool to the registry without a covering probe and
the test fails; add a family without a probe and the structural test fails.

Scope: this is the init-time discovery routine only. It does not touch the
tool-search mechanism itself.
"""

from __future__ import annotations

from typing import Callable

# Default top-k per probe. Mirrors the harness tool_search default (max_results
# ~5) and the observed live behaviour (a single read probe surfaced ~4 tools).
DEFAULT_TOP_K = 5

# The tool families the capture + synthesis paths depend on. This minimum set is
# fixed by the capture-pipeline brief. Extend deliberately — and whenever you add
# a family here you MUST add it to both TOOL_REGISTRY and PROBE_BATTERY, or the
# structural drift test fails.
FAMILIES: tuple[str, ...] = (
    "read",
    "search",
    "patch",
    "create",
    "link",
    "retrieve",
    "graph",
)

# --- source set: family -> the fully-qualified tool names that family requires ---
#
# Names are exactly as the harness exposes them (``mcp__<server>__<tool>``) so the
# union from surface_tools is directly comparable to what a real tool_search
# returns. Servers in play: obsidian (read/search/patch), write-agent
# (create/link), mini-vinny (search/retrieve/graph).
TOOL_REGISTRY: dict[str, frozenset[str]] = {
    "read": frozenset(
        {
            "mcp__obsidian__obsidian_get_file_contents",
            "mcp__obsidian__obsidian_batch_get_file_contents",
        }
    ),
    "search": frozenset(
        {
            "mcp__obsidian__obsidian_simple_search",
            "mcp__obsidian__obsidian_complex_search",
            "mcp__mini-vinny__vault_search",
            "mcp__mini-vinny__retrieve_search",
        }
    ),
    "patch": frozenset(
        {
            "mcp__obsidian__obsidian_patch_content",
            "mcp__obsidian__obsidian_append_content",
        }
    ),
    "create": frozenset(
        {
            "mcp__write-agent__write_create_note",
        }
    ),
    "link": frozenset(
        {
            "mcp__write-agent__write_apply_link_suggestions",
        }
    ),
    "retrieve": frozenset(
        {
            "mcp__mini-vinny__assemble_context",
            "mcp__mini-vinny__retrieve_assemble",
            "mcp__mini-vinny__get_note_with_context",
            "mcp__mini-vinny__notes_get_with_context",
        }
    ),
    "graph": frozenset(
        {
            "mcp__mini-vinny__graph_expand",
            "mcp__mini-vinny__analytics_connect_suggest",
        }
    ),
}

# --- the battery: family -> the fixed tool_search query strings to run ---
#
# Each family's probes are chosen so their union surfaces every tool in
# TOOL_REGISTRY[family] within the top-k of a keyword search, even against a noisy
# universe of unrelated tools. Where one query cannot rank all of a family's tools
# into the top-k (e.g. four search tools split across two servers), a second probe
# widens the coverage. The union over the whole battery is the known-tool set.
PROBE_BATTERY: dict[str, list[str]] = {
    "read": [
        "obsidian read note file contents",
        "obsidian batch read multiple files contents",
    ],
    "search": [
        "obsidian simple complex search vault",
        "semantic vault search retrieve assemble notes",
    ],
    "patch": [
        "obsidian patch content heading append section",
    ],
    "create": [
        "write create new vault note",
    ],
    "link": [
        "write apply labelled link suggestions edges",
    ],
    "retrieve": [
        "assemble context retrieve note neighbourhood",
        "get note notes with context typed neighbours",
    ],
    "graph": [
        "graph expand typed neighbours connect suggest analytics",
    ],
}


def all_registry_tools() -> set[str]:
    """The full source set: every tool name across all families."""
    out: set[str] = set()
    for names in TOOL_REGISTRY.values():
        out |= set(names)
    return out


def surface_tools(
    search_fn: Callable[[str, int], list[str]],
    *,
    top_k: int = DEFAULT_TOP_K,
) -> set[str]:
    """Run the full probe battery and return the UNION of surfaced tool names.

    ``search_fn(query, top_k) -> list[str]`` is the deferred-tool search: the
    harness ``tool_search`` in production, a top-k keyword simulator in tests.
    The whole point of this routine is that callers take the union of the entire
    battery — never the top-k of a single probe.
    """
    surfaced: set[str] = set()
    for family in FAMILIES:
        for query in PROBE_BATTERY[family]:
            surfaced.update(search_fn(query, top_k))
    return surfaced


def print_battery() -> None:
    """Print the battery and registry for human/agent inspection.

    Run ``python -m kbai.tool_battery`` (from the vault root) to see the exact
    ``tool_search`` queries the capture command should run at session start.
    """
    print("Deferred-tool discovery battery — run a tool_search per query, union the results.\n")
    for family in FAMILIES:
        print(f"[{family}]")
        for query in PROBE_BATTERY[family]:
            print(f"  tool_search: {query!r}")
        for name in sorted(TOOL_REGISTRY[family]):
            print(f"    expect: {name}")
        print()
    print(f"Total registry tools: {len(all_registry_tools())}")


if __name__ == "__main__":  # pragma: no cover - manual inspection helper
    print_battery()
