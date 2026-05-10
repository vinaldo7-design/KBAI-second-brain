"""Stage 0 item 9: simple file-backed cache for compiled voice profiles."""

from __future__ import annotations

import json
import os
from pathlib import Path

from .profile import VoiceProfile


def _default_cache_dir() -> Path:
    vault_root = Path(os.environ.get("VAULT_ROOT", "."))
    return vault_root / "06-Maps" / "voice-profiles"


def save_cached_profile(profile: VoiceProfile, cache_dir: Path | None = None) -> Path:
    cache_dir = cache_dir or _default_cache_dir()
    cache_dir.mkdir(parents=True, exist_ok=True)
    p = cache_dir / f"{profile.profile_hash}.json"
    p.write_text(json.dumps(profile.to_dict(), indent=2), encoding="utf-8")
    return p


def load_cached_profile(profile_hash: str, cache_dir: Path | None = None) -> VoiceProfile | None:
    cache_dir = cache_dir or _default_cache_dir()
    p = cache_dir / f"{profile_hash}.json"
    if not p.exists():
        return None
    return VoiceProfile.from_dict(json.loads(p.read_text(encoding="utf-8")))
