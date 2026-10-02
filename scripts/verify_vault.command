#!/bin/bash
# verify_vault.command: run natively (double-click in Finder). Rebuilds the graph, refreshes
# embeddings for changed summaries, then runs the healthcheck, the integrity audit and the tests.
cd "/Users/vinaynair/Library/Mobile Documents/iCloud~md~obsidian/Documents/Second Brain/Second Brain" || exit 1
export HF_HUB_OFFLINE=1
PY=/Users/vinaynair/opt/anaconda3/envs/minivinnymcp/bin/python
LOG=07-attachments/oxford-inbox/_verify_vault.log
echo "== graph ==" | tee "$LOG"
"$PY" vault_graph.py . 2>&1 | tail -3 | tee -a "$LOG"
echo "== embed (incremental) ==" | tee -a "$LOG"
"$PY" vault_embed.py 2>&1 | tail -8 | tee -a "$LOG"
echo "== healthcheck ==" | tee -a "$LOG"
"$PY" healthcheck.py --semantic 2>&1 | tail -5 | tee -a "$LOG"
echo "== audit ==" | tee -a "$LOG"
"$PY" scripts/vault_audit.py 2>&1 | tail -2 | tee -a "$LOG"
echo "== duplicate-gate tests ==" | tee -a "$LOG"
"$PY" -m pytest minivinnymcp/tests/test_collision_gate.py -q -rxXfs -p no:cacheprovider 2>&1 | tail -14 | tee -a "$LOG"
echo "== tests ==" | tee -a "$LOG"
"$PY" -m pytest minivinnymcp/tests writeagentmcp/tests -q -p no:cacheprovider 2>&1 | tail -25 | tee -a "$LOG"
echo "DONE" | tee -a "$LOG"
