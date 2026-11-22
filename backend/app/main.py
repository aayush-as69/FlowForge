import logging
import threading
from datetime import timedelta
import time
from contextlib import asynccontextmanager
from sqlalchemy import text

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import routers
from app.core import db as database
from app.core.db import get_db
from app.core.config import settings
from app.core.security import decode_token
from app.models import ApiMetric, RevokedToken, User
from app.services import runner, seed

log = logging.getLogger("flowforge")
logging.basicConfig(level=logging.INFO)


def _bootstrap():
    import app.workflows.procurement  # noqa: F401

    database.init_db()
    with database.SessionLocal() as db:
        cutoff = database.utcnow() - timedelta(days=settings.api_metric_retention_days)
        db.query(ApiMetric).filter(ApiMetric.ts < cutoff).delete(synchronize_session=False)
        db.query(RevokedToken).filter(RevokedToken.expires_at < database.utcnow()).delete(synchronize_session=False)
        db.commit()
        # Demo identities and fixtures are never provisioned implicitly in production.
        if settings.seed_demo:
            seed.seed_base(db)
            seed.seed_history(db)
    n = runner.resume_interrupted()
    if n:
        log.info("resumed %s interrupted workflow(s)", n)


@asynccontextmanager
async def lifespan(app: FastAPI):
    import app.workflows.procurement  # noqa: F401

    database.init_db()
    thread = threading.Thread(target=_bootstrap, name="bootstrap", daemon=True)
    thread.start()
    yield


app = FastAPI(title="FlowForge API", version="1.0.0", lifespan=lifespan,
              docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)


@app.middleware("http")
async def observe(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001
        log.exception("unhandled error on %s", request.url.path)
        response = JSONResponse({"detail": "Unexpected server error. Please retry; if it persists contact an administrator."}, status_code=500)
    ms = (time.perf_counter() - started) * 1000
    # Resolve tenant from the verified session token; anonymous traffic has no tenant attribution.
    org_id = None
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else request.cookies.get("ff_session")
    payload = decode_token(token) if token else None
    try:
        with database.SessionLocal() as metrics_db:
            if payload:
                try:
                    user = metrics_db.get(User, int(payload["sub"]))
                    if user and user.is_active:
                        org_id = user.org_id
                except (KeyError, TypeError, ValueError):
                    org_id = None
            metrics_db.add(ApiMetric(org_id=org_id, path=request.url.path,
                                     status_code=response.status_code, duration_ms=round(ms)))
            metrics_db.commit()
    except Exception:  # metrics must never break an otherwise healthy response
        log.exception("could not persist API metric")
    return response


@app.exception_handler(RequestValidationError)
async def validation_handler(request: Request, exc: RequestValidationError):
    errors = [{"field": ".".join(str(p) for p in e["loc"][1:]) or str(e["loc"][0]), "message": e["msg"]} for e in exc.errors()]
    return JSONResponse(status_code=422, content={"detail": "Some fields are invalid.", "errors": errors})


for router in routers:
    app.include_router(router, prefix="/api")


@app.get("/api/system/health")
def health(db=Depends(get_db)):
    db.execute(text("SELECT 1"))
    return {"ok": True, "service": "flowforge-api", "database": "up"}
