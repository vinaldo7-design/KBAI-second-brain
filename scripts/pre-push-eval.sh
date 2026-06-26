#!/usr/bin/env bash
# Stage 0 item 7: pre-push eval hook (not yet wired into .git/hooks/).
# Stage 6 will install it as a real pre-push hook with a failure threshold.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

# Prefer an explicit PYTHON_BIN, then a local .venv, then system python.
PY="${PYTHON_BIN:-python}"
if [ -x "$REPO_ROOT/.venv/bin/python" ]; then
  PY="$REPO_ROOT/.venv/bin/python"
fi

"$PY" -m kbai.eval.run_retrieval_eval --dry
