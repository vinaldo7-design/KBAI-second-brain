"""Private history for the notes, which the public code repo ignores.

    python -m kbai.notes_history "message"

The git folder sits outside the vault, so it is not synced to iCloud, and it has no
remote, so notes never leave this machine. Generated files are left out.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

DEFAULT_GIT_DIR = Path.home() / ".local" / "share" / "kbai" / "notes.git"
NOTE_PATHS = [
    *(f":(glob){folder}/**/*.md" for folder in (
        "00-Captures", "01-Ideas", "02-Learning", "03-Projects", "04-Substack", "05-Personal", "06-Maps",
    )),
    "CLAUDE.md",
]


def snapshot(vault_root: Path, message: str, git_dir: Path | None = None) -> str | None:
    """Commit the notes if they changed. Returns the short commit id, or None."""
    git_dir = Path(git_dir or os.environ.get("KBAI_NOTES_GIT_DIR") or DEFAULT_GIT_DIR)

    def git(*args, check=True):
        return subprocess.run(
            ["git", f"--git-dir={git_dir}", f"--work-tree={vault_root}",
             "-c", "user.name=kbai notes", "-c", "user.email=notes@kbai.invalid", *args],
            cwd=vault_root, capture_output=True, text=True, check=check,
        )

    if not git_dir.exists():
        git_dir.mkdir(parents=True)
        git("init", "-q")
    # One add per path: git rejects the whole call if any path matches nothing.
    # -f because the vault's own .gitignore excludes these folders.
    for path in NOTE_PATHS:
        git("add", "-f", "-A", "--", path, check=False)
    if git("diff", "--cached", "--quiet", check=False).returncode == 0:
        return None
    git("commit", "-q", "-m", message)
    return git("rev-parse", "--short", "HEAD").stdout.strip()


if __name__ == "__main__":
    root = Path(os.environ.get("VAULT_ROOT") or Path.cwd())
    commit = snapshot(root, sys.argv[1] if len(sys.argv) > 1 else "snapshot")
    print(f"saved notes as {commit}" if commit else "notes unchanged")
