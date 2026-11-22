import logging
import threading
import time
from contextlib import asynccontextmanager
from sqlalchemy import text

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api import routers
from app.core import db as database
from app.core.db import get_db
from app.core.config import settings
from app.services import runner, seed

log = logging.getLogger("flowforge")
logging.basicConfig(level=logging.INFO)

def _bootstrap():
    import app.workflows.procurement  # noqa: F401  (registers the function definition + exception specs)

    database.init_db()
    with database.SessionLocal() as db:
        seed.seed_base(db)
        if settings.seed_demo:
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
    # Persist request metrics so observability survives restarts and is consistent across workers.
    try:
        with database.SessionLocal() as metrics_db:
            from app.models import ApiMetric
            metrics_db.add(ApiMetric(path=request.url.path, status_code=response.status_code, duration_ms=round(ms)))
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
