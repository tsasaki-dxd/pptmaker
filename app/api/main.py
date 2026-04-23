"""
FastAPI entrypoint. Runs on Lambda via Mangum in Phase 1, and directly with
uvicorn in local/dev.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI
from mangum import Mangum

from .config import get_settings
from .routers import images, projects, templates

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
app.include_router(images.router)


# Schema creation happens lazily inside db.get_session() on the first
# DB-touching request. Doing it in a startup hook used to hide errors
# behind a try/except (a Lambda that couldn't reach RDS at boot would
# come up anyway, then 500 every query with "relation does not exist").
# Lazy + propagate means the actual traceback reaches CloudWatch.


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "env": get_settings().env}


handler = Mangum(app)
