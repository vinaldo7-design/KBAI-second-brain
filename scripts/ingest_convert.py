#!/usr/bin/env python3
"""ingest_convert.py — Stage 1 of the Oxford ingestion pipeline (mechanical, idempotent).

Walks 07-attachments/oxford-inbox/<module>/ for source files (pdf, pptx, docx, vtt, srt, txt, md, html),
converts each to markdown with markitdown, strips subtitle timestamps, and records every file in
07-attachments/oxford-inbox/_manifest.json keyed by sha256 so re-runs skip what is already converted.

The inbox is in vault_graph.py SKIP_DIRS, so nothing here enters the graph, the embedder or the audit.
Output: 07-attachments/oxford-inbox/_md/<module>__<source-stem>.<ext>.md  (one per source file; ext kept so slides and transcript with the same stem never collide)

Usage (vault root):  python3 scripts/ingest_convert.py [--force] [--module M3]
Manifest status per file: converted -> extracted -> pushed (later stages advance it).
"""
import argparse, hashlib, json, re, sys, datetime
from pathlib import Path

INBOX = Path("07-attachments/oxford-inbox")
MD_DIR = INBOX / "_md"
MANIFEST = INBOX / "_manifest.json"
SOURCE_EXT = {".pdf", ".pptx", ".docx", ".vtt", ".srt", ".txt", ".md", ".html", ".htm", ".xlsx", ".csv", ".ipynb"}

def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()

def strip_subtitles(text: str) -> str:
    """VTT/SRT -> plain prose: drop headers, cue numbers, timestamps; merge consecutive lines; dedupe
    the overlapping repeats that auto-captioners emit."""
    lines, out, prev = text.splitlines(), [], ""
    for ln in lines:
        s = ln.strip()
        if not s or s == "WEBVTT" or s.isdigit() or "-->" in s or s.startswith(("NOTE", "Kind:", "Language:")):
            continue
        s = re.sub(r"<[^>]+>", "", s)                      # <v Speaker> tags, <c> styling
        s = re.sub(r"^\[?\d{1,2}:\d{2}(:\d{2})?\]?\s*", "", s)  # leading [hh:mm:ss]
        if s and s != prev:
            out.append(s); prev = s
    # paragraph every ~12 lines so the result is readable rather than one wall
    paras = [" ".join(out[i:i + 12]) for i in range(0, len(out), 12)]
    return "\n\n".join(paras)

BIG_PDF_MB = 30  # above this, markitdown's layout analysis is too slow; pypdf's plain text extractor is used instead

def convert(src: Path) -> str:
    if src.suffix.lower() == ".pdf" and src.stat().st_size > BIG_PDF_MB * 1024 * 1024:
        from pypdf import PdfReader
        pages = []
        for i, page in enumerate(PdfReader(str(src)).pages, 1):
            t = (page.extract_text() or "").strip()
            if t:
                pages.append(f"<!-- page {i} -->\n{t}")
        return "\n\n".join(pages)
    if src.suffix.lower() in {".vtt", ".srt"}:
        return strip_subtitles(src.read_text(encoding="utf-8", errors="replace"))
    if src.suffix.lower() in {".txt", ".md"}:
        return src.read_text(encoding="utf-8", errors="replace")
    from markitdown import MarkItDown
    return MarkItDown().convert(str(src)).text_content

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true", help="re-convert even if the hash is already in the manifest")
    ap.add_argument("--module", help="only this module folder, e.g. M3")
    args = ap.parse_args()
    if not INBOX.exists():
        sys.exit(f"no inbox at {INBOX}")
    MD_DIR.mkdir(exist_ok=True)
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    by_hash = {v["sha256"]: k for k, v in manifest.items()}
    converted = skipped = failed = 0
    for mod_dir in sorted(p for p in INBOX.iterdir() if p.is_dir() and not p.name.startswith("_")):
        if args.module and mod_dir.name != args.module:
            continue
        for src in sorted(p for p in mod_dir.rglob("*") if p.is_file() and p.suffix.lower() in SOURCE_EXT and not p.name.startswith(".")):
            rel = str(src.relative_to(INBOX))
            h = sha256(src)
            if not args.force and h in by_hash and manifest[by_hash[h]].get("status") in {"converted", "extracted", "pushed"}:
                skipped += 1; continue
            out = MD_DIR / f"{mod_dir.name}__{re.sub(r'[^A-Za-z0-9._-]+', '-', src.stem).strip('-')}.{src.suffix.lower().lstrip('.')}.md"
            try:
                text = convert(src)
            except Exception as e:  # keep going; record the failure
                manifest[rel] = {"sha256": h, "module": mod_dir.name, "status": "failed", "error": str(e)[:200],
                                 "converted_at": datetime.datetime.now().isoformat(timespec="seconds")}
                failed += 1; print(f"FAILED  {rel}: {e}")
                MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"); continue
            header = (f"<!-- source: {rel} | sha256: {h[:16]} | converted: {datetime.date.today()} -->\n\n")
            out.write_text(header + text.strip() + "\n", encoding="utf-8")
            manifest[rel] = {"sha256": h, "module": mod_dir.name, "md": str(out.relative_to(INBOX)), "status": "converted",
                             "chars": len(text), "converted_at": datetime.datetime.now().isoformat(timespec="seconds"),
                             "notes_created": [], "notes_updated": []}
            converted += 1; print(f"ok      {rel} -> {out.name} ({len(text):,} chars)", flush=True)
            MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")  # survive a timeout
    MANIFEST.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n")
    print(f"\nconverted {converted}, skipped {skipped} (already in manifest), failed {failed}; manifest: {MANIFEST}")
    sys.exit(1 if failed else 0)

if __name__ == "__main__":
    main()
