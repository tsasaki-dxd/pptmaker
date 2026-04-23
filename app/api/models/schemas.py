"""Pydantic request/response schemas."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field

LayoutKind = Literal["cover", "toc", "section_divider", "content", "about", "disclaimer"]

# Only figure types with a concrete renderer in app/render/figure_renderers/.
# Keep this list in sync with the FIGURE_CATALOG the LLM is given so that
# schema validation mirrors the render pipeline's actual capabilities.
FigureType = Literal[
    "table",
    "cards_grid",
    "two_column",
    "timeline",
    "stat_callout",
    "bullet_list",
    "comparison",
]


class TemplateProfile(BaseModel):
    id: UUID
    tenant_id: str
    name: str
    original_s3_path: str
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    layouts: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime


class TemplateCreateResponse(BaseModel):
    template_id: UUID
    upload_url: str


class ProjectCreate(BaseModel):
    name: str
    template_id: UUID


class Project(BaseModel):
    id: UUID
    tenant_id: str
    name: str
    template_id: UUID
    status: str
    created_at: datetime


class SlideSpec(BaseModel):
    index: int = Field(ge=1)
    layout: LayoutKind
    figure_type: FigureType | None = None
    content: dict[str, Any] = Field(default_factory=dict)


class Blueprint(BaseModel):
    id: UUID
    project_id: UUID
    version: int
    title: str
    slides: list[SlideSpec]
    created_at: datetime


class BlueprintCreate(BaseModel):
    intent: str
    required_sections: list[str] = Field(default_factory=list)
    aux_context: str | None = None
    mode: Literal["freeform", "structured", "import"] = "freeform"


BlueprintJobStatus = Literal["pending", "complete", "failed"]


class BlueprintJob(BaseModel):
    job_id: UUID
    project_id: UUID
    status: BlueprintJobStatus
    blueprint_id: UUID | None = None
    error: str | None = None
    created_at: datetime | None = None


class RevisionCreate(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)


class Revision(BaseModel):
    id: UUID
    blueprint_id: UUID
    instruction: str
    patch: list[dict[str, Any]]
    applied: bool
    created_at: datetime


class RenderRequest(BaseModel):
    blueprint_id: UUID


class RenderResponse(BaseModel):
    job_id: UUID
    blueprint_id: UUID
    status: Literal["queued", "running", "complete", "failed"]


class PreviewResponse(BaseModel):
    slide_index: int
    url: str


class ExportResponse(BaseModel):
    format: Literal["pptx", "pdf"]
    url: str
