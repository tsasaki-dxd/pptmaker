"""
FastAPI entrypoint. Runs on Lambda via Mangum in Phase 1, and directly with
uvicorn in local/dev.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from mangum import Mangum

from .config import get_settings
from .models.db import init_db
from .routers import projects, templates

logging.basicConfig(
    level=get_settings().log_level,
    format='{"ts":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","msg":"%(message)s"}',
)

# CORS is handled entirely by API Gateway (see infra/stacks/app_stack.py
# HttpApi cors_preflight). Not enabling FastAPI's CORSMiddleware — doing
# so would double up `Access-Control-Allow-Origin` headers on responses,
# which browsers reject.
app = FastAPI(title="SlideForge API", version="0.1.0")

app.include_router(templates.router)
app.include_router(projects.router)


@app.on_event("startup")
def _startup() -> None:
    # `create_all` is idempotent — no-op if tables already exist.
    # Safe to run on every Lambda cold start.
    try:
        init_db()
    except Exception as e:
        # Don't let a transient DB issue keep the whole Lambda from coming
        # up; log loudly and let the first actual request surface the
        # error with CORS headers attached.
        logging.getLogger("slideforge.startup").exception("init_db failed: %s", e)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": get_settings().env}


handler = Mangum(app)
