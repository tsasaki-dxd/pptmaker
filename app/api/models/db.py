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
