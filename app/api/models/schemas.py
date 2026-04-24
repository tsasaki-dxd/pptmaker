"""Pydantic request/response schemas."""

from __future__ import annotations

import os
from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field, field_validator, model_validator

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
    "matrix_2x2",
    "swot",
    "pyramid",
    "org_chart",
    "kpi_dashboard",
    "pull_quote",
    "icon_list",
    "process_flow",
    "gantt",
    "stack_bar",
    "waterfall",
    "cost_breakdown",
    "image_slot",
]


class TemplateProfile(BaseModel):
    id: UUID
    tenant_id: str
    name: str
    original_s3_path: str
    design_tokens: dict[str, Any] = Field(default_factory=dict)
    layouts: list[dict[str, Any]] = Field(default_factory=list)
    template_slide_count: int = 0
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
    # Which template page this slide is rendered from. Auto-assigned by
    # cycling through the template's pages if left None; user can
    # override per-slide via PATCH on the blueprint. The render Lambda
    # uses this to copy the chosen template page's XML and overlay
    # blueprint content.
    template_slide_index: int | None = Field(default=None, ge=1)
    # Phase 2 scaffold (§4.4/§5.5): one-sentence conclusion shown as the
    # slide's headline. Optional now; becomes required in Phase 2.2.
    headline_message: str | None = Field(default=None, max_length=200)

    @field_validator("headline_message")
    @classmethod
    def _validate_headline_message(cls, v: str | None) -> str | None:
        if v is None:
            return None
        s = v.strip()
        if not s:
            raise ValueError("headline_message must not be blank if provided")
        # §3.2 rule: must be a complete sentence ending with sentence punctuation (half or full width).
        if not s.endswith(("。", "！", "？", ".", "!", "?")):
            raise ValueError("headline_message must end with sentence punctuation (。！？.!?)")
        return s

    @model_validator(mode="after")
    def _enforce_headline_required(self) -> SlideSpec:
        # Flag gate: when FF_HEADLINE_REQUIRED=1, headline_message must be present.
        if os.environ.get("FF_HEADLINE_REQUIRED") == "1" and self.headline_message is None:
            raise ValueError("headline_message is required when FF_HEADLINE_REQUIRED=1")
        return self


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


class SlideTemplateMapping(BaseModel):
    """One row in a PATCH /blueprint payload: slide N uses template page T."""

    index: int = Field(ge=1)
    template_slide_index: int = Field(ge=1)


class SlideMappingPatch(BaseModel):
    mappings: list[SlideTemplateMapping]


class RevisionCreate(BaseModel):
    instruction: str = Field(min_length=1, max_length=2000)
    # 1-based slide index to scope the revision to. When set, the LLM
    # is instructed to only modify /slides/{index-1}/... and the server
    # rejects any patch op that escapes that subtree. Lets the UI fire
    # "rewrite this one slide" without risking bleed into siblings.
    slide_index: int | None = Field(default=None, ge=1)


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


class ImageAssetCreateRequest(BaseModel):
    mime: Literal["image/png", "image/jpeg", "image/webp"]
    bytes: int = Field(gt=0, le=10_485_760)  # 10 MB


class ImageAssetCreateResponse(BaseModel):
    asset_id: UUID
    upload_url: str
    fields: dict[str, str]  # presigned POST form fields


class ImageAssetCommitRequest(BaseModel):
    checksum_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class ImageAsset(BaseModel):
    id: UUID
    tenant_id: str
    project_id: UUID
    s3_key: str
    mime: str
    bytes: int
    width_px: int | None = None
    height_px: int | None = None
    checksum_sha256: str | None = None
    created_at: datetime
