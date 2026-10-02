#!/usr/bin/env python3
"""ingest_push.py — Stage 5 of the Oxford ingestion pipeline. Run NATIVELY on the Mac with the
server's interpreter so the full write path fires for every note: schema gate, kebab-id check,
no-overwrite, write journal, on-write embedding and edge hooks. Identical to write_create_note,
minus the MCP round trip.

Usage (vault root):
  HF_HUB_OFFLINE=1 /Users/vinaynair/opt/anaconda3/envs/minivinnymcp/bin/python scripts/ingest_push.py 07-attachments/oxford-inbox/_payloads_M1.json [--dryrun]

Payload file: a JSON list of {folder, note_id, frontmatter, body}, produced by the orchestrator after
Vinay's approval. Notes that already exist are reported and skipped (the writer refuses to overwrite).
"""
import json, re, sys, time
from pathlib import Path
sys.path.insert(0, str(Path.cwd()))
from kbai.storage.note_creator import create_note

NOTE_DIRS = ["00-Captures", "01-Ideas", "02-Learning", "03-Projects", "04-Substack", "05-Personal", "06-Maps"]
_ID_RE = re.compile(r"^id:\s*'?\"?(\d{12})'?\"?\s*$", re.M)

def existing_numeric_ids(root):
    """Frontmatter `id:` of every note already in the vault -> note stem.
    The writer's own gates check the filename, not the numeric id, so a batch
    whose id counter overlaps an earlier batch would be written happily
    (2026-10-01: Module 4 reused 34 of Module 3's ids). This gate stops that."""
    ids = {}
    for d in NOTE_DIRS:
        for f in (root / d).glob("*.md"):
            head = f.read_text(encoding="utf-8", errors="ignore")[:600]
            m = _ID_RE.search(head)
            if m:
                ids[m.group(1)] = f.stem
    return ids

def id_collisions(payloads, root):
    seen = existing_numeric_ids(root)
    out = []
    for p in payloads:
        nid = str(p["frontmatter"].get("id", ""))
        if (root / p["folder"] / f"{p['note_id']}.md").exists():
            continue  # already written on an earlier run; skipped below
        if nid in seen:
            out.append((p["note_id"], nid, seen[nid]))
        seen[nid] = p["note_id"]
    return out

def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    payloads = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    dryrun = "--dryrun" in sys.argv
    root = Path.cwd()
    clashes = id_collisions(payloads, root)
    if clashes:
        for stem, nid, other in clashes:
            print(f"ID CLASH {stem}: frontmatter id {nid} already used by {other}")
        sys.exit(f"\n{len(clashes)} numeric id collision(s); nothing written. Renumber the payload and re-run.")
    ok = skipped = failed = 0
    t0 = time.time()
    for p in payloads:
        target = root / p["folder"] / f"{p['note_id']}.md"
        if target.exists():
            skipped += 1; print(f"skip    {p['folder']}/{p['note_id']} (exists)"); continue
        r = create_note(root, p["folder"], p["note_id"], p["frontmatter"], p["body"], dryrun=dryrun)
        d = r.model_dump() if hasattr(r, "model_dump") else dict(r)
        if d.get("status") in ("applied", "dry_run"):
            ok += 1; print(f"{d['status']:8}{p['folder']}/{p['note_id']}  journal={d.get('journal_id')}")
        else:
            failed += 1; print(f"FAILED  {p['folder']}/{p['note_id']}: {d.get('reason') or d.get('message')}")
    print(f"\n{ok} written, {skipped} skipped (already present), {failed} failed, {time.time()-t0:.1f}s")
    print("next: python3 vault_graph.py . && python3 scripts/vault_audit.py && python3 healthcheck.py --semantic")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
