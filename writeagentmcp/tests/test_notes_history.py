"""Notes are git-ignored in the code repo. This keeps their history in a private
repo outside the vault, with no remote."""

import subprocess

import pytest

from kbai import notes_history


@pytest.fixture
def vault(tmp_path):
    root = tmp_path / "vault"
    (root / "01-Ideas").mkdir(parents=True)
    (root / "06-Maps").mkdir()
    (root / "01-Ideas" / "a.md").write_text("one\n")
    (root / "06-Maps" / "m.md").write_text("map\n")
    (root / "06-Maps" / "vault-graph.json").write_text("{}\n")
    (root / "CLAUDE.md").write_text("rules\n")
    (root / ".gitignore").write_text("01-Ideas/\n06-Maps/\nCLAUDE.md\n")
    return root


@pytest.fixture
def git_dir(tmp_path):
    return tmp_path / "elsewhere" / "notes.git"


def _git(git_dir, vault, *args):
    return subprocess.run(
        ["git", f"--git-dir={git_dir}", f"--work-tree={vault}", *args],
        capture_output=True, text=True, check=True,
    ).stdout


def test_first_snapshot_records_notes_even_though_the_vault_ignores_them(vault, git_dir):
    assert notes_history.snapshot(vault, "first", git_dir=git_dir)
    tracked = _git(git_dir, vault, "ls-files").split()
    assert {"01-Ideas/a.md", "06-Maps/m.md", "CLAUDE.md"} <= set(tracked)


def test_generated_files_are_left_out(vault, git_dir):
    notes_history.snapshot(vault, "first", git_dir=git_dir)
    assert "06-Maps/vault-graph.json" not in _git(git_dir, vault, "ls-files").split()


def test_history_lives_outside_the_vault(vault, git_dir):
    notes_history.snapshot(vault, "first", git_dir=git_dir)
    assert git_dir.exists() and not (vault / ".git").exists()


def test_no_change_makes_no_commit(vault, git_dir):
    notes_history.snapshot(vault, "first", git_dir=git_dir)
    assert notes_history.snapshot(vault, "second", git_dir=git_dir) is None


def test_edits_and_deletions_can_be_recovered(vault, git_dir):
    first = notes_history.snapshot(vault, "first", git_dir=git_dir)
    (vault / "01-Ideas" / "a.md").write_text("two\n")
    assert notes_history.snapshot(vault, "edit", git_dir=git_dir)
    (vault / "01-Ideas" / "a.md").unlink()
    assert notes_history.snapshot(vault, "delete", git_dir=git_dir)
    assert _git(git_dir, vault, "show", f"{first}:01-Ideas/a.md") == "one\n"


def test_the_repo_has_no_remote(vault, git_dir):
    notes_history.snapshot(vault, "first", git_dir=git_dir)
    assert _git(git_dir, vault, "remote") == ""
