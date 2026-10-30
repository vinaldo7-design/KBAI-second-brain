"""The MCP servers must run with HF_HUB_OFFLINE=1.

Models are cached locally. Without this flag, loading one first checks
huggingface.co, and when that check fails the hub retries with backoff. Measured
2026-10-30: 72s for the embedding model and 48s for the reranker, which exceeds
the 60s tool-call cap on the first search after a server start.
"""

import json
from pathlib import Path

import pytest

VAULT_ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("package", ["minivinnymcp", "writeagentmcp"])
def test_config_snippet_runs_offline(package):
    snippet = json.loads((VAULT_ROOT / package / "claude_desktop_config_snippet.json").read_text())
    servers = snippet.get("mcpServers", snippet)
    for server in servers.values():
        assert server["env"].get("HF_HUB_OFFLINE") == "1"
