import logging
import threading
from datetime import timedelta
import time
from concurrent.futures import ThreadPoolExecutor
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
        _purge_old_rows(db)
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


_IS_PROD = settings.app_env in {"production", "prod"}
app = FastAPI(title="FlowForge API", version="1.0.0", lifespan=lifespan, redoc_url=None,
              docs_url=None if _IS_PROD else "/api/docs", openapi_url=None if _IS_PROD else "/api/openapi.json")

MAX_BODY_BYTES = 256 * 1024  # request bodies are short JSON documents; anything larger is refused up front
_UNSAFE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
_PURGE_EVERY = 500  # records between retention sweeps of the metrics table
_records_since_purge = 0
_purge_lock = threading.Lock()


def _purge_old_rows(db) -> None:
    cutoff = database.utcnow() - timedelta(days=settings.api_metric_retention_days)
    db.query(ApiMetric).filter(ApiMetric.ts < cutoff).delete(synchronize_session=False)
    db.query(RevokedToken).filter(RevokedToken.expires_at < database.utcnow()).delete(synchronize_session=False)


@app.middleware("http")
async def request_guards(request: Request, call_next):
    """Cheap rejects before any work: oversized bodies and cross-site state changes."""
    try:
        declared = int(request.headers.get("content-length", "0") or 0)
    except ValueError:
        declared = 0
    if declared > MAX_BODY_BYTES:
        return JSONResponse({"detail": "Request body is too large."}, status_code=413)
    origin = request.headers.get("origin")
    if request.method in _UNSAFE_METHODS and origin and origin != "null":
        host = request.headers.get("x-forwarded-host") or request.headers.get("host", "")
        if origin.split("://", 1)[-1].lower() != host.lower():
            return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
    elif request.method in _UNSAFE_METHODS and origin == "null":
        return JSONResponse({"detail": "Cross-site request refused."}, status_code=403)
    return await call_next(request)


@app.middleware("http")
async def observe(request: Request, call_next):
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:  # noqa: BLE001
        log.exception("unhandled error on %s", request.url.path)
        response = JSONResponse({"detail": "Unexpected server error. Please retry; if it persists contact an administrator."}, status_code=500)
    ms = (time.perf_counter() - started) * 1000
    # Tenant is resolved from the verified session token in the background writer; anonymous traffic is never stored.
    auth = request.headers.get("authorization", "")
    token = auth[7:].strip() if auth.lower().startswith("bearer ") else request.cookies.get("ff_session")
    payload = decode_token(token) if token else None
    # Metrics are only read per organisation, so anonymous traffic and unmatched (404) paths are never stored:
    # otherwise anyone could grow the table with arbitrary URLs.
    if not payload or request.scope.get("route") is None:
        return response
    # The lookup and insert run on a single background worker so they never add latency to the response.
    _submit_metric(payload.get("sub"), request.url.path[:300], response.status_code, round(ms))
    return response


_metrics_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="ff-metrics")
_metrics_pending = 0
_METRICS_MAX_PENDING = 2000  # under sustained overload, drop samples rather than queue without bound


def _submit_metric(sub, path: str, status_code: int, duration_ms: int) -> None:
    global _metrics_pending
    with _purge_lock:
        if _metrics_pending >= _METRICS_MAX_PENDING:
            return
        _metrics_pending += 1
    _metrics_pool.submit(_persist_metric, sub, path, status_code, duration_ms)


def drain_metrics() -> None:
    """Block until queued metric writes have finished (used by tests and graceful shutdown)."""
    _metrics_pool.submit(lambda: None).result()


def _persist_metric(sub, path: str, status_code: int, duration_ms: int) -> None:
    global _records_since_purge, _metrics_pending
    try:
        with database.SessionLocal() as metrics_db:
            try:
                user = metrics_db.get(User, int(sub))
                org_id = user.org_id if user and user.is_active else None
            except (TypeError, ValueError):
                org_id = None
            if org_id is None:
                return
            metrics_db.add(ApiMetric(org_id=org_id, path=path, status_code=status_code, duration_ms=duration_ms))
            with _purge_lock:
                _records_since_purge += 1
                due = _records_since_purge >= _PURGE_EVERY
                if due:
                    _records_since_purge = 0
            if due:
                _purge_old_rows(metrics_db)
            metrics_db.commit()
    except Exception:  # metrics must never break anything
        log.exception("could not persist API metric")
    finally:
        with _purge_lock:
            _metrics_pending -= 1



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
