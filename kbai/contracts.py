"""Stage 2: typed contracts for KBAI module + agent boundaries.

Design principles:
- Match the *current* dict shapes returned by MCP tools so adoption is
  incremental — existing dicts validate against these models without
  rewrites.
- `extra="allow"` on every model so additive fields don't break consumers.
- MCP boundary stays dict on the wire; modules can pass typed models
  internally and serialise via `.model_dump()` at the adapter layer.

Stage 2 ships the schemas. Stage 3+ wires modules to use them.

Stage 5.5 will add: CognitiveProfile, ProfileComparison.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# Tolerant config — every model permits extra fields. New tool versions can
# add response keys without breaking pre-existing parsers.
_MODEL_CFG = ConfigDict(extra="allow")


# --- Graph primitives -----------------------------------------------------


class Edge(BaseModel):
    """Typed directed edge between two notes."""

    model_config = _MODEL_CFG

    source: str | None = None
    target: str | None = None
    edge_type: str | None = Field(default=None, alias="type")
    direction: Literal["in", "out"] | None = None
    annotation: str | None = None
    weight: float | None = None
    target_exists: bool = True

    # Convenience: graph_expand emits hops with `note_id` instead of source/target
    note_id: str | None = None
    hop: int | None = None


class Note(BaseModel):
    """A vault note as surfaced through `notes_get_with_context`."""

    model_config = _MODEL_CFG

    note_id: str
    title: str | None = None
    summary: str | None = None
    content: str | None = None
    edges: list[Edge] = Field(default_factory=list)


# --- Retrieval primitives -------------------------------------------------


class RetrievalResult(BaseModel):
    """A single ranked note returned by `vault_search` / `retrieve_search`."""

    model_config = _MODEL_CFG

    note_id: str
    score: float | None = None
    title: str | None = None
    summary: str | None = None
    filepath: str | None = None


class ReasoningStep(BaseModel):
    """One step in a reasoning_path attribution."""

    # Need populate_by_name so the model also accepts `from_` (the Python attr
    # name) on input, not only the `from` alias. Roundtrip safety: the model
    # can be dumped and re-parsed without by_alias=True everywhere.
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    from_: str = Field(alias="from")
    edge: str
    to: str


class ContextNote(BaseModel):
    """A note in an assemble_context result."""

    model_config = _MODEL_CFG

    note_id: str
    title: str | None = None
    summary: str | None = None
    content: str | None = None
    composite_score: float | None = None
    source: Literal["seed", "ppr"] | None = None
    via_edge: str | None = None
    parent: str | None = None
    reasoning_path: list[ReasoningStep] | None = None


class Context(BaseModel):
    """Result of `assemble_context` / `retrieve_assemble`."""

    model_config = _MODEL_CFG

    query: str
    notes: list[ContextNote] = Field(default_factory=list)
    chars_used: int = 0
    char_budget: int = 0
    mode: Literal["standard", "sparring", "exhaustive"] | None = None


class ExpansionHop(BaseModel):
    """One hop result from graph_expand."""

    model_config = _MODEL_CFG

    note_id: str
    title: str | None = None
    summary: str | None = None
    edge_type: str
    direction: Literal["in", "out"]
    weight: float
    annotation: str | None = None
    hop: int


class ExpansionResult(BaseModel):
    """Result of `graph_expand`."""

    model_config = _MODEL_CFG

    note_id: str
    title: str | None = None
    summary: str | None = None
    hops: list[ExpansionHop] = Field(default_factory=list)


class AuditCandidate(BaseModel):
    """One row in an audit_taxonomy result."""

    model_config = _MODEL_CFG

    source: str
    target: str
    score: float
    annotation: str | None = None
    source_summary: str | None = None
    target_summary: str | None = None


class SuggestionEntry(BaseModel):
    """One row in an analytics_connect_suggest category list."""

    model_config = _MODEL_CFG

    source: str
    target: str | None = None
    suggested_type: str | None = None
    current_type: str | None = None
    confidence: Any = None  # int, float, or "structural" sentinel
    reason: str | None = None


# --- Research primitives --------------------------------------------------


class Source(BaseModel):
    model_config = _MODEL_CFG
    title: str | None = None
    url: str | None = None
    summary: str | None = None
    published: str | None = None


class ClaimCheck(BaseModel):
    model_config = _MODEL_CFG
    claim_snippet: str
    verdict: Literal["supports", "contradicts", "mixed", "uncertain"] = "uncertain"
    evidence: list[dict] = Field(default_factory=list)


class CrossLink(BaseModel):
    model_config = _MODEL_CFG
    hint_text: str | None = None
    reason: str | None = None
    vault_note_id: str | None = None  # populated by perplexity adapter's matcher


class OpenQuestion(BaseModel):
    model_config = _MODEL_CFG
    question: str
    reason: str | None = None


class ResearchPayload(BaseModel):
    """Result of `research_note`."""

    model_config = _MODEL_CFG

    note_id: str
    researched_at: str | datetime | None = None
    model: str | None = None
    sources: list[Source] = Field(default_factory=list)
    claim_checks: list[ClaimCheck] = Field(default_factory=list)
    cross_links: list[CrossLink] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    raw_summary: str = ""


# --- Write Agent primitives -----------------------------------------------


class WriteReceipt(BaseModel):
    """Receipt returned by every Write Agent tool. Stage 0 stubs return
    these with applied=False; Stage 3 will populate hash_before / hash_after
    and journal_id."""

    model_config = _MODEL_CFG

    status: Literal[
        "stub",
        "applied",
        "dryrun",
        "dry_run",
        "rejected",
        "error",
        "already_present",
        "patched",
        "no_section",
        "missing_file",
    ] = "stub"
    tool: str
    note_id: str | None = None
    applied: bool = False
    would_apply: bool | None = None
    dryrun: bool | None = None

    # Stage 3+ fields
    hash_before: str | None = None
    hash_after: str | None = None
    diff_summary: str | None = None
    journal_id: int | None = None
    file: str | None = None
    section_chars: int | None = None
    ts: str | None = None
    applied_at: str | None = None

    # Stage 0 stub diagnostic fields
    stage: int | None = None
    message: str | None = None


# --- Cognitive routing (Stage 5.5 schemas, defined now for stability) ----


class CognitiveProfile(BaseModel):
    """Thinking-fidelity profile. Modifies retrieval, ranking, path selection.
    Distinct from voice_profile (which only changes rendering).

    v1 ships functional profiles only: default, skeptic, operator, builder.
    Person-named profiles (e.g. `vinay`) are calibrated, not declared — see
    Stage 8 in docs/refactor-plan.md.
    """

    model_config = _MODEL_CFG

    profile_id: str
    display_name: str
    schema_version: int = 1
    edge_weight_overrides: dict[str, float] = Field(default_factory=dict)
    contradiction_policy: Literal["suppress", "allow", "seek"] = "suppress"
    mention_policy: Literal["ignore", "exhaustive"] = "ignore"
    path_length_preference: Literal["short", "balanced", "deep"] = "balanced"
    abstraction_preference: Literal["concrete", "balanced", "abstract"] = "balanced"
    restart_bias_tags: dict[str, float] = Field(default_factory=dict)
    confidence_threshold: float = 0.0
    notes: str = ""


class ProfileComparison(BaseModel):
    """Result of `cognition_compare_profiles` (Stage 5.6)."""

    model_config = _MODEL_CFG

    query: str
    profiles: list[str]
    per_profile: dict[str, list[ContextNote]] = Field(default_factory=dict)
    divergence_score: float | None = None  # Jaccard distance over top-N sets
    overlap_top_n: int = 15


# --- Council Mode (Stage 5.6) --------------------------------------------


class CouncilProfileResult(BaseModel):
    """One profile's contribution to a CouncilEvidence bundle."""

    model_config = _MODEL_CFG

    profile_id: str
    display_name: str
    focus_summary: str  # one-line machine summary of what this lens prioritises
    notes: list[ContextNote] = Field(default_factory=list)


class CouncilEvidence(BaseModel):
    """Result of `council_retrieve`. Same query run through N profiles,
    with overlap analysis. Synthesizer (Claude) reads this and writes
    the final answer via the /council slash command."""

    model_config = _MODEL_CFG

    query: str
    profiles: list[str]
    per_profile: list[CouncilProfileResult] = Field(default_factory=list)

    # Overlap analysis over the union of top-k note ids.
    consensus: list[str] = Field(default_factory=list)  # ≥2 profiles surfaced it
    unanimous: list[str] = Field(default_factory=list)   # all profiles surfaced it
    unique_to: dict[str, list[str]] = Field(default_factory=dict)  # profile_id → ids only it surfaced

    top_k: int = 10
    coverage_count: int = 0  # total distinct note ids across profiles
