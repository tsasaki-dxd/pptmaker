"""Render-entry wiring of `ensure_slots_populated` (Phase 2 §11).

These tests exercise the helper that the render HTTP endpoint calls to
lazy-migrate a pre-2.1 TemplateProfile row to the v1.1 shape (slots +
fixed_elements). Heavy monkeypatching keeps them hermetic: no real DB
sessions, no real S3, no Pydantic roundtrip details.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from api.routers import projects as projects_router


def _row(layouts: list[dict[str, Any]]) -> SimpleNamespace:
    """Fake TemplateProfileRow: attributes only, no SQLAlchemy machinery."""
    return SimpleNamespace(
        id=str(uuid4()),
        tenant_id="t1",
        name="tmpl",
        original_s3_path="s3://bucket/tenants/t1/templates/abc.pptx",
        design_tokens={},
        layouts=layouts,
        template_slide_count=len(layouts),
        created_at=datetime.now(UTC),
    )


def test_v1_0_profile_triggers_ensure_slots_populated_with_download_bytes_fetcher(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _row(
        [
            {"index": 1, "layout": "cover", "confidence": 0.95, "reason": "r"},
            {"index": 2, "layout": "content", "confidence": 0.6, "reason": "r"},
        ]
    )

    captured: dict[str, Any] = {}

    def fake_ensure(profile: Any, pptx_fetcher: Any) -> Any:
        captured["profile"] = profile
        captured["pptx_fetcher"] = pptx_fetcher
        new_layouts = [
            {**lo, "slots": [], "fixed_elements": []} for lo in profile.layouts
        ]
        return profile.model_copy(update={"layouts": new_layouts})

    monkeypatch.setattr(projects_router, "ensure_slots_populated", fake_ensure)

    db = MagicMock()
    projects_router._migrate_template_slots_if_needed(db, row)

    assert "profile" in captured, "ensure_slots_populated was not called"
    assert captured["pptx_fetcher"] is projects_router.download_bytes
    assert captured["profile"].original_s3_path == row.original_s3_path

    for layout in row.layouts:
        assert "slots" in layout
        assert "fixed_elements" in layout
    db.commit.assert_called_once()


def test_v1_1_profile_fast_path_no_db_write(monkeypatch: pytest.MonkeyPatch) -> None:
    row = _row(
        [
            {
                "index": 1,
                "layout": "cover",
                "confidence": 0.95,
                "reason": "r",
                "slots": [],
                "fixed_elements": [],
            }
        ]
    )

    call_count = {"n": 0}

    def fake_ensure(profile: Any, pptx_fetcher: Any) -> Any:
        call_count["n"] += 1
        return profile

    monkeypatch.setattr(projects_router, "ensure_slots_populated", fake_ensure)

    db = MagicMock()
    projects_router._migrate_template_slots_if_needed(db, row)

    assert call_count["n"] == 1
    db.commit.assert_not_called()
    db.rollback.assert_not_called()


def test_fetch_returns_none_no_persistence_warning_logged_render_proceeds(
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    row = _row(
        [{"index": 1, "layout": "cover", "confidence": 0.95, "reason": "r"}]
    )
    original_layouts = row.layouts

    def fake_download(_s3_path: str) -> bytes | None:
        return None

    monkeypatch.setattr(projects_router, "download_bytes", fake_download)

    with caplog.at_level(logging.WARNING, logger="slideforge.template"):
        db = MagicMock()
        projects_router._migrate_template_slots_if_needed(db, row)

    db.commit.assert_not_called()
    assert row.layouts is original_layouts
    assert any(
        "pptx_fetcher returned None" in r.getMessage() for r in caplog.records
    )
