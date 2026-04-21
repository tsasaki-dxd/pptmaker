"""
FastAPI entrypoint. Runs on Lambda via Mangum in Phase 1, and directly with
uvicorn in local/dev.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from .config import get_settings
from .models.db import init_db
from .routers import projects, templates

logging.basicConfig(
    level=get_settings().log_level,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}',
)

app = FastAPI(title="SlideForge API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Phase 1 内部利用。Phase 2 で絞る
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(templates.router)
app.include_router(projects.router)


@app.on_event("startup")
def _startup() -> None:
    if get_settings().env in ("local", "dev"):
        init_db()


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": get_settings().env}


handler = Mangum(app)
