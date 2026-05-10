#!/usr/bin/env bash
# Stage 0 item 7: pre-push eval hook (not yet wired into .git/hooks/).
# Stage 6 will install it as a real pre-push hook with a failure threshold.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Use the minivinnymcp conda env if it exists; otherwise system python.
PY="${PYTHON_BIN:-python}"
if [ -x "/Users/vinaynair/opt/anaconda3/envs/minivinnymcp/bin/python" ]; then
  PY="/Users/vinaynair/opt/anaconda3/envs/minivinnymcp/bin/python"
fi

"$PY" -m kbai.eval.run_retrieval_eval --dry
