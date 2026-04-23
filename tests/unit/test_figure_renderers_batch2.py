"""Validate / render tests for org_chart, kpi_dashboard, pull_quote, icon_list, process_flow."""

from __future__ import annotations

import re

from render.figure_renderers import list_capabilities, renderer_for
from render.figure_renderers.base import EMUBox, RenderContext
from render.shapes import DEFAULT_FONT, DEFAULT_PALETTE

_OFF_EXT_RE = re.compile(r'<a:(?:off|ext)\s+(?:x|y|cx|cy)="([^"]+)"')
_NEW_TYPES = ("org_chart", "kpi_dashboard", "pull_quote", "icon_list", "process_flow")


def _ctx() -> RenderContext:
    return RenderContext(palette=DEFAULT_PALETTE, font=DEFAULT_FONT, next_shape_id=1000)


def _box() -> EMUBox:
    return EMUBox(x=457200, y=1463040, w=11246400, h=4937760)


def _assert_int_emu(shapes_xml: list[str]) -> None:
    for xml in shapes_xml:
        for raw in _OFF_EXT_RE.findall(xml):
            assert raw.lstrip("-").isdigit(), f"non-integer EMU coord: {raw!r}"


def test_batch2_types_listed_in_capabilities() -> None:
    ftypes = {c["figure_type"] for c in list_capabilities()}
    for expected in _NEW_TYPES:
        assert expected in ftypes


def test_org_chart_registry_lookup() -> None:
    r = renderer_for("org_chart")
    assert r.figure_type == "org_chart"


def test_org_chart_rejects_missing_fields() -> None:
    r = renderer_for("org_chart")
    assert not r.validate({}).ok
    assert not r.validate({"nodes": []}).ok
    assert not r.validate({"nodes": [{"id": "a"}]}).ok
    assert not r.validate({"nodes": [{"label": "missing-id"}]}).ok
    assert not r.validate(
        {"nodes": [{"id": "a", "label": "A", "parent": "b"}]}
    ).ok


def test_org_chart_renders() -> None:
    r = renderer_for("org_chart")
    content = {
        "nodes": [
            {"id": "ceo", "label": "CEO"},
            {"id": "cto", "label": "CTO", "parent": "ceo"},
            {"id": "cfo", "label": "CFO", "parent": "ceo"},
            {"id": "eng", "label": "ENG", "parent": "cto"},
            {"id": "fin", "label": "FIN", "parent": "cfo"},
        ]
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    assert out.next_shape_id > 1000
    _assert_int_emu(out.shapes_xml)


def test_kpi_dashboard_registry_lookup() -> None:
    r = renderer_for("kpi_dashboard")
    assert r.figure_type == "kpi_dashboard"


def test_kpi_dashboard_rejects_missing_fields() -> None:
    r = renderer_for("kpi_dashboard")
    assert not r.validate({}).ok
    assert not r.validate({"metrics": []}).ok
    assert not r.validate({"metrics": [{"value": "1", "label": "x"}]}).ok
    assert not r.validate(
        {"metrics": [{"value": "1"} for _ in range(3)]}
    ).ok
    assert not r.validate(
        {"metrics": [{"label": "x"} for _ in range(3)]}
    ).ok
    assert not r.validate(
        {"metrics": [{"value": "1", "label": "x"} for _ in range(7)]}
    ).ok


def test_kpi_dashboard_renders_3_cards() -> None:
    r = renderer_for("kpi_dashboard")
    content = {
        "metrics": [
            {"value": "120", "label": "Users", "delta": "+5%"},
            {"value": "80", "label": "MRR"},
            {"value": "99.9%", "label": "Uptime", "delta": "-0.1%"},
        ]
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)


def test_kpi_dashboard_renders_6_cards() -> None:
    r = renderer_for("kpi_dashboard")
    content = {
        "metrics": [{"value": str(i), "label": f"L{i}"} for i in range(6)]
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)


def test_pull_quote_registry_lookup() -> None:
    r = renderer_for("pull_quote")
    assert r.figure_type == "pull_quote"


def test_pull_quote_rejects_missing_fields() -> None:
    r = renderer_for("pull_quote")
    assert not r.validate({}).ok
    assert not r.validate({"quote": ""}).ok
    assert not r.validate({"quote": "   "}).ok
    assert not r.validate({"attribution": "X"}).ok


def test_pull_quote_renders() -> None:
    r = renderer_for("pull_quote")
    content = {"quote": "Vision without execution is hallucination.", "attribution": "Edison"}
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)


def test_pull_quote_truncates_long_text() -> None:
    r = renderer_for("pull_quote")
    content = {"quote": "a" * 500}
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)


def test_icon_list_registry_lookup() -> None:
    r = renderer_for("icon_list")
    assert r.figure_type == "icon_list"


def test_icon_list_rejects_missing_fields() -> None:
    r = renderer_for("icon_list")
    assert not r.validate({}).ok
    assert not r.validate({"items": []}).ok
    assert not r.validate({"items": [{"icon": "★"}]}).ok
    assert not r.validate({"items": ["not-an-object"]}).ok


def test_icon_list_renders() -> None:
    r = renderer_for("icon_list")
    content = {
        "items": [
            {"icon": "★", "title": "Speed", "body": "高速"},
            {"icon": "◆", "title": "Quality"},
            {"title": "Cost", "body": "低減"},
        ]
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)


def test_process_flow_registry_lookup() -> None:
    r = renderer_for("process_flow")
    assert r.figure_type == "process_flow"


def test_process_flow_rejects_missing_fields() -> None:
    r = renderer_for("process_flow")
    assert not r.validate({}).ok
    assert not r.validate({"steps": []}).ok
    assert not r.validate({"steps": [{"label": "A"}, {"label": "B"}]}).ok
    assert not r.validate({"steps": [{"body": "no-label"} for _ in range(3)]}).ok
    assert not r.validate(
        {"steps": [{"label": f"s{i}"} for i in range(7)]}
    ).ok


def test_process_flow_renders() -> None:
    r = renderer_for("process_flow")
    content = {
        "steps": [
            {"label": "Plan", "body": "計画"},
            {"label": "Build"},
            {"label": "Ship", "body": "出荷"},
        ]
    }
    assert r.validate(content).ok
    out = r.render(content, _box(), _ctx())
    assert len(out.shapes_xml) >= 1
    _assert_int_emu(out.shapes_xml)
