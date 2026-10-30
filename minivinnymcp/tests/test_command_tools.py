"""Every Mini Vinny tool a slash command names must exist on the server. Commands
are plain text, so a renamed or removed tool otherwise fails only when used."""

import asyncio
import re
from pathlib import Path

_vault_root = Path(__file__).parent.parent.parent

import minivinnymcp.server as mv  # noqa: E402


def test_commands_only_name_tools_that_exist():
    tools = {t.name for t in asyncio.run(mv.app.list_tools())}
    missing = {
        f"{path.name}: {name}"
        for path in (_vault_root / "claude" / "commands").glob("*.md")
        for name in re.findall(r"mcp__mini-vinny__(\w+)", path.read_text(encoding="utf-8"))
        if name not in tools
    }
    assert not missing, sorted(missing)
