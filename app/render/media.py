"""Media registry for embedded image assets (Phase 2.3 Track J)."""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ImageAssetDescriptor:
    asset_id: str
    s3_key: str
    mime: str
    width_px: int | None
    height_px: int | None


@dataclass
class MediaRegistry:
    entries: dict[str, ImageAssetDescriptor] = field(default_factory=dict)
    slide_usages: dict[int, set[str]] = field(default_factory=dict)
    resolved: dict[str, ImageAssetDescriptor] = field(default_factory=dict)

    def register(self, desc: ImageAssetDescriptor, slide_index: int) -> str:
        if desc.asset_id not in self.entries:
            self.entries[desc.asset_id] = desc
        rid = self._rid_for(desc.asset_id)
        self.slide_usages.setdefault(slide_index, set()).add(rid)
        return rid

    def _rid_for(self, asset_id: str) -> str:
        idx = list(self.entries.keys()).index(asset_id)
        return f"rId{10000 + idx}"
