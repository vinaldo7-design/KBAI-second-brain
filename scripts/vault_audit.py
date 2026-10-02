#!/usr/bin/env python3
"""vault_audit.py — read-only integrity audit over every note. Run after each ingest batch.

Checks: frontmatter validity via kbai.schema (the same gate the writer uses), folder/type
agreement, duplicate ids, broken wikilinks, non-kebab tags, edge-heading case drift, and
idea/concept notes below the two-labelled-link minimum. Exit 1 if anything fails.
Usage (from vault root):  python3 scripts/vault_audit.py
"""
import os, re, sys, collections, yaml
sys.path.insert(0, os.getcwd())
from kbai.schema import validate_frontmatter, DEPRECATED_FRONTMATTER
NOTE_DIRS = ["00-Captures","01-Ideas","02-Learning","03-Projects","04-Substack","05-Personal","06-Maps"]
EXEMPT = {"README.md","connect-suggestions.md"}          # not notes: generated or folder docs
FOLDER_TYPE = {"00-Captures":{"capture"},"01-Ideas":{"idea","concept"},"02-Learning":{"learning"},
               "03-Projects":{"project"},"04-Substack":{"essay"},"05-Personal":{"personal"},"06-Maps":{"map"}}
EDGE_HEADS = ["builds on","builds toward","contradicts","analogous to","exemplifies","challenges","operationalises"]
CANON = {h: h.capitalize() for h in EDGE_HEADS + ["referenced in maps"]}
link_re = re.compile(r"\[\[([^\]|#]+)(?:#[^\]|]*)?(?:\|[^\]]*)?\]\]")
notes = {}
for d in NOTE_DIRS:
    for root,_,files in os.walk(d):
        for fn in files:
            if fn.endswith(".md") and fn not in EXEMPT:
                p = os.path.join(root,fn); notes[fn[:-3]] = (d,p,open(p,encoding="utf-8").read())
stems = set(notes)
F = collections.defaultdict(list)
ids = collections.defaultdict(list)
for stem,(d,p,txt) in sorted(notes.items()):
    m = re.match(r"^---\n(.*?)\n---\n", txt, re.S)
    if not m: F["schema"].append(f"{p}: no frontmatter"); continue
    try: fm = yaml.safe_load(m.group(1)) or {}
    except Exception as e: F["schema"].append(f"{p}: yaml error {e}"); continue
    body = txt[m.end():]
    err = validate_frontmatter(fm)
    if err: F["schema"].append(f"{p}: {err}")
    dep = DEPRECATED_FRONTMATTER & fm.keys()
    if dep: F["schema"].append(f"{p}: deprecated keys {sorted(dep)}")
    if fm.get("type") and fm["type"] not in FOLDER_TYPE.get(d,{fm["type"]}): F["folder"].append(f"{p}: type {fm['type']} in {d}")
    if " " in stem or stem != stem.lower(): F["filename"].append(f"{p}: not kebab-case")
    ids[str(fm.get("id"))].append(stem)
    for t in fm.get("tags") or []:
        if isinstance(t,str) and not re.fullmatch(r"(topic|lens)/[a-z0-9]+(-[a-z0-9]+)*", t): F["tags"].append(f"{stem}: {t}")
    for l in link_re.findall(body):
        l = l.strip()
        if l and l not in stems and not l.lower().endswith((".png",".pdf",".canvas",".jpg",".jpeg")): F["links"].append(f"{stem} -> [[{l}]]")
    for h in re.findall(r"^###\s+(.+?)\s*$", body, re.M):
        if h.lower() in CANON and h != CANON[h.lower()]: F["headings"].append(f"{stem}: '### {h}'")
    if fm.get("type") in ("idea","concept"):
        n = 0
        for h in EDGE_HEADS:
            sec = re.search(r"###\s+"+re.escape(h)+r"\s*\n(.*?)(?=\n###|\n## |\Z)", body, re.S|re.I)
            if sec: n += len(link_re.findall(sec.group(1)))
        if n < 2: F["underlinked"].append(f"{stem} ({n})")
for k,v in ids.items():
    if len(v) > 1: F["duplicate-ids"].append(f"{k}: {v}")
print(f"notes audited: {len(notes)}")
hard = ["schema","folder","filename","duplicate-ids","tags","headings"]
for k in hard + ["links","underlinked"]:
    if F[k]:
        print(f"\n== {k.upper()} ({len(F[k])}){'' if k in hard else '  [advisory]'}")
        for line in F[k]: print("  " + line)
fails = sum(len(F[k]) for k in hard)
print(f"\nRESULT: {'PASS' if fails == 0 else f'FAIL ({fails} hard issues)'}; advisory: {len(F['links'])} dangling links, {len(F['underlinked'])} under-linked idea notes")
sys.exit(1 if fails else 0)
