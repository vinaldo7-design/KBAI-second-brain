#!/usr/bin/env python3
"""ingest_snapshot.py — Stage 2 prerequisite. Writes a compact snapshot of what the vault already says
(id, type, tags, summary for every note) to 07-attachments/oxford-inbox/_vault_snapshot.json.

Extraction agents work in parallel with NO vault tools; this file is how each one checks a candidate
claim against the existing corpus before proposing it. Regenerate it after every push (it reads
06-Maps/vault-graph.json, so run `python3 vault_graph.py .` first).
Usage (vault root):  python3 scripts/ingest_snapshot.py
"""
import json, sys
from pathlib import Path
g = Path("06-Maps/vault-graph.json")
if not g.exists():
    sys.exit("run `python3 vault_graph.py .` first")
import re, yaml
nodes = json.loads(g.read_text())["nodes"]
def tags_of(fp):
    try:
        txt = Path(fp).read_text(encoding="utf-8"); m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
        return (yaml.safe_load(m.group(1)) or {}).get("tags", []) if m else []
    except Exception:
        return []
snap = [{"id": n["id"], "type": n.get("type"), "tags": tags_of(n.get("filepath") or n.get("path") or ""), "summary": (n.get("summary") or "").strip()}
        for n in nodes if isinstance(n.get("summary"), str) and n["summary"].strip()]
out = Path("07-attachments/oxford-inbox/_vault_snapshot.json")
out.write_text(json.dumps(snap, ensure_ascii=False, indent=0) + "\n")
print(f"{len(snap)} notes -> {out} ({out.stat().st_size // 1024} KB)")
