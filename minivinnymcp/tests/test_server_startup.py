"""MCP servers must answer the initialize handshake quickly: the ML stack loads
after start, not at import. It costs 6s+ warm and up to about 50s cold."""

import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

_vault_root = Path(__file__).resolve().parents[2]
os.environ.setdefault("VAULT_ROOT", str(_vault_root))
sys.path.insert(0, str(_vault_root))

import minivinnymcp.server as mv  # noqa: E402

LOAD_MINI_VINNY = (
    "import importlib.util as u; "
    "s = u.spec_from_file_location('srv', 'minivinnymcp/server.py'); "
    "m = u.module_from_spec(s); s.loader.exec_module(m)"
)


@pytest.mark.parametrize(
    "load",
    [LOAD_MINI_VINNY, "import writeagentmcp.server", "import vault_search"],
    ids=["mini-vinny", "write-agent", "vault_search"],
)
def test_import_does_not_load_the_ml_stack(load):
    probe = (
        f"import sys; {load}; "
        "heavy = [m for m in ('sentence_transformers', 'torch', 'transformers') if m in sys.modules]; "
        "sys.exit(f'loaded at import: {heavy}' if heavy else 0)"
    )
    env = {**os.environ, "VAULT_ROOT": str(_vault_root), "PYTHONPATH": str(_vault_root)}
    result = subprocess.run(
        [sys.executable, "-c", probe],
        capture_output=True, text=True, env=env, cwd=_vault_root, timeout=180,
    )
    assert result.returncode == 0, result.stderr[-500:]


def test_concurrent_callers_load_the_model_once(monkeypatch):
    built = []
    gate = threading.Barrier(4)

    def load():
        built.append(1)
        return object()

    monkeypatch.setattr(mv, "_load_model", load)
    monkeypatch.setattr(mv, "_model", None)
    got = []

    def call():
        gate.wait()
        got.append(mv._get_model())

    threads = [threading.Thread(target=call) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(built) == 1
    assert len({id(m) for m in got}) == 1


def test_warm_up_loads_both_models(monkeypatch):
    seen = []
    monkeypatch.setattr(mv, "_get_model", lambda: seen.append("embed"))
    monkeypatch.setattr(mv, "_get_reranker", lambda: seen.append("rerank"))
    mv._warm_models()
    assert seen == ["embed", "rerank"]


def test_warm_up_failure_is_not_fatal(monkeypatch):
    def boom():
        raise RuntimeError("no model")

    monkeypatch.setattr(mv, "_get_model", boom)
    mv._warm_models()  # must not raise: the first search reports the real error
