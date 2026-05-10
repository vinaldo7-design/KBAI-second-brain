"""Stage 0 item 9: VoiceProfile placeholder. Real synthesis lands later
once the `/voice vinay` activation work is unblocked (Milestone 4)."""

from __future__ import annotations

from dataclasses import dataclass, field, asdict


@dataclass
class VoiceProfile:
    profile_hash: str
    exemplar_ids: list[str] = field(default_factory=list)
    profile_data: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "VoiceProfile":
        return cls(
            profile_hash=d["profile_hash"],
            exemplar_ids=list(d.get("exemplar_ids") or []),
            profile_data=dict(d.get("profile_data") or {}),
        )


def build_voice_profile(
    profile_hash: str,
    exemplar_ids: list[str] | None = None,
    profile_data: dict | None = None,
) -> VoiceProfile:
    return VoiceProfile(
        profile_hash=profile_hash,
        exemplar_ids=list(exemplar_ids or []),
        profile_data=dict(profile_data or {}),
    )
