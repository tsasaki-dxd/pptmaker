"""SQLAlchemy models and session management."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, create_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship, sessionmaker

from ..config import get_db_url


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(200))
    plan: Mapped[str] = mapped_column(String(50), default="internal")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TemplateProfileRow(Base):
    __tablename__ = "template_profiles"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    name: Mapped[str] = mapped_column(String(200))
    original_s3_path: Mapped[str] = mapped_column(String(500))
    design_tokens: Mapped[dict] = mapped_column(JSON, default=dict)
    layouts: Mapped[list] = mapped_column(JSON, default=list)
    # Number of slide{N}.xml files inside the uploaded .pptx. 0 means
    # not yet analyzed; populated lazily on first GET /api/templates/{id}.
    template_slide_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProjectRow(Base):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    # Cognito `sub` of the user who created the project. Projects are
    # user-scoped: only the owner sees them in their list. Legacy rows
    # created before this column existed are NULL and are visible to
    # everyone in the tenant for backward compatibility.
    owner_user_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(200))
    template_id: Mapped[str] = mapped_column(String(36), ForeignKey("template_profiles.id"))
    status: Mapped[str] = mapped_column(String(50), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    blueprints: Mapped[list[BlueprintRow]] = relationship(back_populates="project")


class BlueprintRow(Base):
    __tablename__ = "blueprints"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    title: Mapped[str] = mapped_column(String(200))
    slides: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    project: Mapped[ProjectRow] = relationship(back_populates="blueprints")


class RevisionRow(Base):
    __tablename__ = "revisions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    blueprint_id: Mapped[str] = mapped_column(String(36), ForeignKey("blueprints.id"), index=True)
    instruction: Mapped[str] = mapped_column(String(2000))
    patch: Mapped[list] = mapped_column(JSON)
    applied: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class OutputRow(Base):
    __tablename__ = "outputs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    blueprint_id: Mapped[str] = mapped_column(String(36), index=True)
    format: Mapped[str] = mapped_column(String(10))
    s3_path: Mapped[str] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ImageAssetRow(Base):
    """User-uploaded image referenced by one or more slides.

    Created by POST /api/projects/{id}/images (returns presigned POST),
    then marked committed by POST /images/{asset_id}/commit once the
    client has uploaded and computed the SHA-256. The render pipeline
    embeds committed assets into the output .pptx.
    """

    __tablename__ = "image_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    s3_key: Mapped[str] = mapped_column(String(500), unique=True)
    mime: Mapped[str] = mapped_column(String(50))
    bytes: Mapped[int] = mapped_column(Integer)
    width_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height_px: Mapped[int | None] = mapped_column(Integer, nullable=True)
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    uploaded_by: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class BlueprintJobRow(Base):
    """Async blueprint-generation job.

    Created immediately by POST /api/projects/{id}/blueprint, enqueued to
    SQS, and picked up by the blueprint_worker Lambda which writes the
    resulting BlueprintRow and flips status to "complete" (or "failed").
    The client polls GET /api/projects/{id}/blueprint/job/{job_id}.
    """

    __tablename__ = "blueprint_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|complete|failed
    blueprint_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


class RevisionJobRow(Base):
    """Async revision (per-slide / whole-deck) job.

    Same lifecycle as BlueprintJobRow but the worker calls the
    revision LLM, applies the JSON Patch, and writes a new
    BlueprintRow + RevisionRow on success. Split out from the
    inline /revise path because LLM latency reliably exceeds the
    API Gateway 29s integration timeout, which left the client
    seeing 503/400/500 even when the underlying revision had
    actually committed.
    """

    __tablename__ = "revision_jobs"
    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(String(36), ForeignKey("projects.id"), index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), index=True)
    instruction: Mapped[str] = mapped_column(String(2000))
    slide_index: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|complete|failed
    blueprint_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )


_engine = None
_SessionLocal = None
_tables_ready = False


def get_engine():
    global _engine, _SessionLocal
    if _engine is None:
        _engine = create_engine(get_db_url(), pool_pre_ping=True)
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    return _engine


def _ensure_tables() -> None:
    # Create tables lazily on first DB access instead of at Mangum startup.
    # Startup-time failures used to be swallowed (main.py), leaving the
    # Lambda serving every query against a DB with no tables and 500-ing
    # with "relation does not exist". Running this inline means a DB/SM
    # outage surfaces on the request that triggered it, with a real
    # traceback.
    global _tables_ready
    if _tables_ready:
        return
    engine = get_engine()
    Base.metadata.create_all(engine)
    _add_missing_columns(engine)
    _tables_ready = True


def _add_missing_columns(engine) -> None:
    """Tiny in-place migration for columns added after a table existed.
    create_all() is a no-op on tables that already exist, so it never
    adds new columns. Phase 1 doesn't run Alembic, so we ALTER TABLE
    here. PostgreSQL ADD COLUMN IF NOT EXISTS is idempotent; SQLite
    test DBs are recreated each run so they don't need the migration.
    """
    from sqlalchemy import text

    if engine.dialect.name != "postgresql":
        return
    statements = [
        "ALTER TABLE template_profiles "
        "ADD COLUMN IF NOT EXISTS template_slide_count INTEGER DEFAULT 0",
        "ALTER TABLE projects ADD COLUMN IF NOT EXISTS owner_user_id VARCHAR(200)",
        "CREATE INDEX IF NOT EXISTS ix_projects_owner_user_id "
        "ON projects (owner_user_id)",
    ]
    with engine.begin() as conn:
        for stmt in statements:
            conn.execute(text(stmt))


def get_session():
    _ensure_tables()
    assert _SessionLocal is not None
    db = _SessionLocal()
    try:
        yield db
    finally:
        db.close()


def new_session():
    """Plain (non-generator) session for use outside FastAPI's dependency
    injection. Caller is responsible for commit/rollback/close.
    """
    _ensure_tables()
    assert _SessionLocal is not None
    return _SessionLocal()


def init_db() -> None:
    _ensure_tables()
