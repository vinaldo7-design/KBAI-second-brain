"""Cognitive profile registry.

Profiles live as YAML files under `kbai/cognitive_routing/profiles/`.
Each yaml is one CognitiveProfile (see kbai.contracts).

`load_profile` reads one by id; `list_profiles` enumerates the directory.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from kbai.contracts import CognitiveProfile

PROFILES_DIR = Path(__file__).parent / "profiles"


def list_profile_ids(profiles_dir: Path | None = None) -> list[str]:
    d = profiles_dir or PROFILES_DIR
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.yaml"))


def load_profile(profile_id: str, profiles_dir: Path | None = None) -> CognitiveProfile:
    d = profiles_dir or PROFILES_DIR
    p = d / f"{profile_id}.yaml"
    if not p.exists():
        raise FileNotFoundError(f"Cognitive profile not found: {profile_id} (looked in {d})")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return CognitiveProfile(**data)


def list_profiles(profiles_dir: Path | None = None) -> list[CognitiveProfile]:
    return [load_profile(pid, profiles_dir) for pid in list_profile_ids(profiles_dir)]
