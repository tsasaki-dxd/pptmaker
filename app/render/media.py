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
    # Optional in-memory bytes. When set, ``finalize_media`` writes
    # these directly instead of calling ``fetcher(s3_key)``. Used for
    # icons and other render-time-generated assets that have no S3
    # backing object.
    inline_bytes: bytes | None = None


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

    def register_inline(
        self,
        asset_id: str,
        slide_index: int,
        data: bytes,
        mime: str = "image/png",
    ) -> str:
        """Convenience for inline assets (icons, generated images).

        First call for a given ``asset_id`` stores the bytes; subsequent
        calls dedup — the same icon used on N slides is embedded once.
        """
        if asset_id not in self.entries:
            self.entries[asset_id] = ImageAssetDescriptor(
                asset_id=asset_id,
                s3_key=f"inline://{asset_id}",
                mime=mime,
                width_px=None,
                height_px=None,
                inline_bytes=data,
            )
        rid = self._rid_for(asset_id)
        self.slide_usages.setdefault(slide_index, set()).add(rid)
        return rid

    def _rid_for(self, asset_id: str) -> str:
        idx = list(self.entries.keys()).index(asset_id)
        return f"rId{10000 + idx}"
