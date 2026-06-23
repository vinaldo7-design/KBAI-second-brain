#!/usr/bin/env python3
"""
vault_graph.py — parse an Obsidian vault into a typed JSON graph.

Usage:
    python vault_graph.py <vault_path> [output_path]

Emits a single JSON file with three top-level keys:
    nodes      — one entry per parsed note
    edges      — typed directed edges between notes
    validation — orphans, broken links, schema drift

Edge types (closed set, see vault_taxonomy.yaml):
    builds-on, builds-toward, contradicts, analogous-to,
    exemplifies, challenges, operationalises,
    referenced-in, untyped, mentioned
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

import yaml

# --- Configuration ------------------------------------------------------------

SKIP_DIRS = {"Templates", "07-attachments", ".obsidian", ".trash", "claude", "docs",
             # code packages — infrastructure, not vault content. kbai/templates/*.md
             # in particular are skeletons, not notes; parsing them injected 7 bogus
             # nodes (placeholder summaries) into the graph and broke vault_embed.
             "kbai", "minivinnymcp", "writeagentmcp", "perplexitymcp", "scripts",
             "eval", "__pycache__"}
SKIP_FILES = {"CLAUDE.md", "CLAUDE-static.md", "README.md",
              "vault-manifest.md", "connect-suggestions.md",
              "Untitled.md", "ggg.md"}

# Maps a section heading (lowercased, stripped) to an edge type.
# This is a fallback — vault_taxonomy.yaml is canonical and is loaded at runtime
# by load_taxonomy(). Keep this dict in sync with the yaml so the parser still
# works if the yaml file is missing.
TYPED_LINK_SECTIONS = {
    "builds on": "builds-on",
    "builds toward": "builds-toward",
    "contradicts": "contradicts",
    "analogous to": "analogous-to",
    "exemplifies": "exemplifies",
    "challenges": "challenges",
    "operationalises": "operationalises",
    "referenced in maps": "referenced-in",
}

# A generic "## Links" section without typed sub-headings -> untyped edges.
UNTYPED_LINK_SECTION_NAMES = {"links", "entry points", "connected maps"}

from kbai.schema import DEPRECATED_FRONTMATTER, REQUIRED_FRONTMATTER  # noqa: E402

FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n(.*)$", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]|#]+?)(?:\|[^\]]+)?(?:#[^\]]+)?\]\]")
# A line starting with `- ` optionally followed by a wikilink.
BULLET_WIKILINK_RE = re.compile(r"^\s*[-*]\s+\[\[([^\]|#]+?)(?:\|[^\]]+)?(?:#[^\]]+)?\]\](.*)$")
DATAVIEW_BLOCK_RE = re.compile(r"```dataview.*?```", re.DOTALL)


# --- Data classes -------------------------------------------------------------

@dataclass
class Node:
    id: str                          # filename stem — the wikilink target
    path: str                        # vault-relative path
    folder: str                      # top-level folder
    file_id: Optional[str] = None    # frontmatter id (timestamp)
    title: Optional[str] = None
    type: Optional[str] = None
    status: Optional[str] = None
    summary: Optional[str] = None
    topics: list[str] = field(default_factory=list)
    lenses: list[str] = field(default_factory=list)
    created: Optional[str] = None
    updated: Optional[str] = None
    origin: Optional[str] = None
    raw_frontmatter: dict = field(default_factory=dict)


@dataclass
class Edge:
    source: str
    target: str
    type: str
    annotation: Optional[str] = None
    target_exists: bool = True
    source_file: Optional[str] = None


# --- Taxonomy -----------------------------------------------------------------

def load_taxonomy(vault_root: Path) -> tuple[dict, set, dict]:
    """Read vault_taxonomy.yaml and return (typed_sections, untyped_sections, type_metadata).
    Falls back to module-level constants if the file is absent.
    """
    taxonomy_path = vault_root / "vault_taxonomy.yaml"
    if not taxonomy_path.exists():
        return TYPED_LINK_SECTIONS, UNTYPED_LINK_SECTION_NAMES, {}

    with open(taxonomy_path, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    edge_types = data.get("edge_types", {})
    typed_sections = {
        meta["section_heading"]: et
        for et, meta in edge_types.items()
        if meta.get("section_heading")
    }
    untyped_sections = set(data.get("untyped_section_names", []))
    type_metadata = dict(edge_types)

    if not typed_sections:
        typed_sections = TYPED_LINK_SECTIONS
    if not untyped_sections:
        untyped_sections = UNTYPED_LINK_SECTION_NAMES

    return typed_sections, untyped_sections, type_metadata


# --- Parsing ------------------------------------------------------------------

def split_frontmatter(text: str) -> tuple[dict, str]:
    """Return (frontmatter_dict, body). Empty dict if no frontmatter."""
    match = FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    try:
        fm = yaml.safe_load(match.group(1)) or {}
    except yaml.YAMLError:
        fm = {}
    return fm, match.group(2)


def classify_tags(tags) -> tuple[list[str], list[str]]:
    """Split `topic/x` and `lens/y` tags into two lists."""
    if not tags:
        return [], []
    # YAML can yield list, string, or None. Normalise.
    if isinstance(tags, str):
        tags = [tags]
    topics, lenses = [], []
    for t in tags:
        if not isinstance(t, str):
            continue
        if t.startswith("topic/"):
            topics.append(t[len("topic/"):])
        elif t.startswith("lens/"):
            lenses.append(t[len("lens/"):])
    return topics, lenses


def strip_dataview(body: str) -> str:
    """Remove fenced dataview blocks so we don't parse their syntax as content."""
    return DATAVIEW_BLOCK_RE.sub("", body)


def parse_link_sections(
    body: str,
    typed_sections: Optional[dict] = None,
    untyped_section_names: Optional[set] = None,
) -> list[tuple[str, str, Optional[str]]]:
    """
    Walk the body line by line, tracking current section heading.
    Yield (edge_type, target, annotation) for each bullet wikilink found
    inside a recognised link section.

    Inline wikilinks outside any link section are returned with edge_type
    'mentioned' at the end, so the caller can rank them separately.
    """
    _typed = typed_sections if typed_sections is not None else TYPED_LINK_SECTIONS
    _untyped = untyped_section_names if untyped_section_names is not None else UNTYPED_LINK_SECTION_NAMES

    results: list[tuple[str, str, Optional[str]]] = []
    mentioned: list[tuple[str, str, Optional[str]]] = []

    current_section: Optional[str] = None
    in_links_block = False  # true while we're under a Links-related heading

    for line in body.splitlines():
        heading_match = re.match(r"^(#{2,6})\s+(.+?)\s*$", line)
        if heading_match:
            heading_text = heading_match.group(2).strip().lower()
            # Strip trailing punctuation that sometimes sneaks in
            heading_text = heading_text.rstrip(":").strip()

            if heading_text in _typed:
                current_section = _typed[heading_text]
                in_links_block = True
            elif heading_text in _untyped:
                current_section = "untyped"
                in_links_block = True
            else:
                # Any other heading closes the links block.
                # But only if we're at ## level or the same level.
                level = len(heading_match.group(1))
                if level <= 3:
                    current_section = None
                    in_links_block = False
            continue

        if in_links_block and current_section:
            m = BULLET_WIKILINK_RE.match(line)
            if m:
                target = m.group(1).strip()
                tail = m.group(2).strip()
                annotation = _clean_annotation(tail)
                results.append((current_section, target, annotation))
        else:
            # Track inline wikilinks outside link sections as "mentioned".
            for m in WIKILINK_RE.finditer(line):
                mentioned.append(("mentioned", m.group(1).strip(), None))

    return results + mentioned


def _clean_annotation(tail: str) -> Optional[str]:
    """Normalise the text after a wikilink in a bullet."""
    if not tail:
        return None
    # Strip leading em-dash / hyphen / colon
    tail = re.sub(r"^\s*[—–\-:]+\s*", "", tail).strip()
    return tail or None


def parse_note(
    path: Path,
    vault_root: Path,
    typed_sections: Optional[dict] = None,
    untyped_section_names: Optional[set] = None,
) -> tuple[Node, list[Edge], list[dict]]:
    """Parse one markdown file. Returns (node, edges, issues)."""
    rel_path = path.relative_to(vault_root)
    folder = rel_path.parts[0] if len(rel_path.parts) > 1 else ""
    stem = path.stem

    text = path.read_text(encoding="utf-8")
    fm, body = split_frontmatter(text)

    topics, lenses = classify_tags(fm.get("tags"))

    node = Node(
        id=stem,
        path=str(rel_path).replace("\\", "/"),
        folder=folder,
        file_id=str(fm["id"]) if fm.get("id") is not None else None,
        title=fm.get("title"),
        type=fm.get("type"),
        status=fm.get("status"),
        summary=fm.get("summary"),
        topics=topics,
        lenses=lenses,
        created=str(fm["created"]) if fm.get("created") else None,
        updated=str(fm["updated"]) if fm.get("updated") else None,
        origin=fm.get("origin"),
        raw_frontmatter=fm,
    )

    issues: list[dict] = []

    # Schema checks
    missing = [f for f in REQUIRED_FRONTMATTER if f not in fm]
    if missing:
        issues.append({
            "kind": "missing_frontmatter_field",
            "node": stem,
            "path": node.path,
            "fields": missing,
        })

    deprecated = [f for f in DEPRECATED_FRONTMATTER if f in fm]
    if deprecated:
        issues.append({
            "kind": "deprecated_frontmatter_field",
            "node": stem,
            "path": node.path,
            "fields": deprecated,
        })

    # Extract edges
    clean_body = strip_dataview(body)
    raw_edges = parse_link_sections(clean_body, typed_sections, untyped_section_names)

    edges: list[Edge] = []
    seen = set()  # dedupe (target, type) pairs within one note
    for edge_type, target, annotation in raw_edges:
        key = (edge_type, target)
        if key in seen:
            continue
        seen.add(key)
        edges.append(Edge(
            source=stem,
            target=target,
            type=edge_type,
            annotation=annotation,
            source_file=node.path,
        ))

    return node, edges, issues


# --- Vault walking ------------------------------------------------------------

def walk_vault(vault_root: Path) -> list[Path]:
    """Return all markdown files not in skip lists."""
    notes: list[Path] = []
    for path in vault_root.rglob("*.md"):
        rel_parts = path.relative_to(vault_root).parts
        if any(part in SKIP_DIRS for part in rel_parts):
            continue
        if path.name in SKIP_FILES:
            continue
        notes.append(path)
    return sorted(notes)


# --- Validation ---------------------------------------------------------------

def validate(nodes: dict[str, Node], edges: list[Edge]) -> dict:
    """Run graph-level checks. Mutates edges to set target_exists."""
    existing = set(nodes.keys())

    # Mark broken edges
    broken = []
    for e in edges:
        if e.target not in existing:
            e.target_exists = False
            broken.append({
                "source": e.source,
                "target": e.target,
                "type": e.type,
                "source_file": e.source_file,
            })

    # Compute indegree/outdegree using typed edges only (exclude 'mentioned')
    indegree: dict[str, int] = {nid: 0 for nid in nodes}
    outdegree: dict[str, int] = {nid: 0 for nid in nodes}
    for e in edges:
        if e.type == "mentioned":
            continue
        if e.target in indegree:
            indegree[e.target] += 1
        outdegree[e.source] += 1

    orphans = sorted([
        nid for nid in nodes
        if indegree[nid] == 0 and outdegree[nid] == 0
    ])

    # Wrong-folder checks based on declared type
    expected_folder = {
        "idea": "01-Ideas",
        "learning": "02-Learning",
        "project": "03-Projects",
        "essay": "04-Substack",
        "personal": "05-Personal",
        "map": "06-Maps",
        "capture": "00-Captures",
        "quick-capture": "00-Captures",
    }
    folder_mismatches = []
    for nid, n in nodes.items():
        exp = expected_folder.get(n.type)
        if exp and n.folder != exp:
            folder_mismatches.append({
                "node": nid,
                "path": n.path,
                "declared_type": n.type,
                "expected_folder": exp,
                "actual_folder": n.folder,
            })

    # Link-count checks (minimums per contract)
    min_typed_edges = {"idea": 2, "learning": 1, "essay": 2, "personal": 1}
    undersourced = []
    for nid, n in nodes.items():
        threshold = min_typed_edges.get(n.type)
        if threshold is None:
            continue
        typed_out = sum(
            1 for e in edges
            if e.source == nid and e.type not in ("mentioned", "untyped")
        )
        # Count untyped toward learning/essay/personal minimums since their
        # note format doesn't enforce the typed taxonomy.
        if n.type in ("learning", "essay", "personal"):
            typed_out += sum(1 for e in edges if e.source == nid and e.type == "untyped")
        if typed_out < threshold:
            undersourced.append({
                "node": nid,
                "path": n.path,
                "type": n.type,
                "typed_outgoing": typed_out,
                "minimum": threshold,
            })

    return {
        "summary": {
            "node_count": len(nodes),
            "edge_count": len(edges),
            "typed_edge_count": sum(1 for e in edges if e.type not in ("mentioned", "untyped")),
            "untyped_edge_count": sum(1 for e in edges if e.type == "untyped"),
            "mentioned_edge_count": sum(1 for e in edges if e.type == "mentioned"),
            "broken_edge_count": len(broken),
            "orphan_count": len(orphans),
        },
        "orphans": orphans,
        "broken_edges": broken,
        "folder_mismatches": folder_mismatches,
        "undersourced_notes": undersourced,
    }


# --- Main ---------------------------------------------------------------------

def build_graph(vault_root: Path) -> dict:
    nodes: dict[str, Node] = {}
    edges: list[Edge] = []
    frontmatter_issues: list[dict] = []

    typed_sections, untyped_sections, _type_meta = load_taxonomy(vault_root)

    for path in walk_vault(vault_root):
        node, note_edges, issues = parse_note(path, vault_root, typed_sections, untyped_sections)
        if node.id in nodes:
            frontmatter_issues.append({
                "kind": "duplicate_filename_stem",
                "node": node.id,
                "path": node.path,
                "existing_path": nodes[node.id].path,
            })
            continue
        nodes[node.id] = node
        edges.extend(note_edges)
        frontmatter_issues.extend(issues)

    validation = validate(nodes, edges)
    validation["frontmatter_issues"] = frontmatter_issues

    return {
        "generated_at": None,  # filled in at write time
        "vault_root": str(vault_root),
        "nodes": [asdict(n) for n in nodes.values()],
        "edges": [asdict(e) for e in edges],
        "validation": validation,
    }


def _json_default(obj):
    """Handle types PyYAML produces that json cannot serialise by default."""
    import datetime as _dt
    if isinstance(obj, (_dt.date, _dt.datetime)):
        return obj.isoformat()
    if isinstance(obj, set):
        return sorted(obj)
    return str(obj)


def main():
    if len(sys.argv) < 2:
        print("Usage: python vault_graph.py <vault_path> [output_path]", file=sys.stderr)
        sys.exit(1)

    vault_root = Path(sys.argv[1]).resolve()
    if not vault_root.is_dir():
        print(f"Not a directory: {vault_root}", file=sys.stderr)
        sys.exit(1)

    output_path = (
        Path(sys.argv[2]).resolve()
        if len(sys.argv) >= 3
        else vault_root / "06-Maps" / "vault-graph.json"
    )

    import datetime as _dt
    graph = build_graph(vault_root)
    graph["generated_at"] = _dt.datetime.now().isoformat(timespec="seconds")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(graph, indent=2, ensure_ascii=False, default=_json_default),
        encoding="utf-8",
    )

    s = graph["validation"]["summary"]
    print(f"Wrote {output_path}")
    print(f"  {s['node_count']} nodes, {s['edge_count']} edges "
          f"({s['typed_edge_count']} typed, {s['untyped_edge_count']} untyped, "
          f"{s['mentioned_edge_count']} mentioned)")
    print(f"  {s['broken_edge_count']} broken, {s['orphan_count']} orphans")


if __name__ == "__main__":
    main()
