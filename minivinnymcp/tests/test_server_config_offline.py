"""The MCP servers must run with HF_HUB_OFFLINE=1.

Models are cached locally. Without this flag, loading one first checks
huggingface.co, and when that check fails the hub retries with backoff. Measured
2026-10-30: 72s for the embedding model and 48s for the reranker, which exceeds
the 60s tool-call cap on the first search after a server start.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

VAULT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("package", ["minivinnymcp", "writeagentmcp"])
def test_config_snippet_runs_offline(package):
    snippet = json.loads((VAULT_ROOT / package / "claude_desktop_config_snippet.json").read_text())
    servers = snippet.get("mcpServers", snippet)
    for server in servers.values():
        assert server["env"].get("HF_HUB_OFFLINE") == "1"


# Claude Desktop can rewrite its config and drop the env block (seen 2026-10-30),
# so the servers must default to offline without it.
LOAD_MINI_VINNY = (
    "import importlib.util as u; "
    "s = u.spec_from_file_location('srv', 'minivinnymcp/server.py'); "
    "m = u.module_from_spec(s); s.loader.exec_module(m)"
)


@pytest.mark.parametrize(
    "load",
    [LOAD_MINI_VINNY, "import writeagentmcp.server"],
    ids=["mini-vinny", "write-agent"],
)
def test_server_defaults_to_offline_without_config(load):
    env = {k: v for k, v in os.environ.items() if k != "HF_HUB_OFFLINE"}
    env.update(VAULT_ROOT=str(VAULT_ROOT), PYTHONPATH=str(VAULT_ROOT))
    probe = f"{load}; import os; assert os.environ['HF_HUB_OFFLINE'] == '1'"
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, env=env, cwd=VAULT_ROOT, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-500:]
