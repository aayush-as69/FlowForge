"""Entry point: `python backend/run.py` (used by Next.js instrumentation in production)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
libs = os.path.join(HERE, ".pylibs")
if os.path.isdir(libs):
    sys.path.insert(0, libs)

import uvicorn  # noqa: E402

from app.core.config import settings  # noqa: E402

if __name__ == "__main__":
    uvicorn.run("app.main:app", host="127.0.0.1", port=settings.port, log_level="info")
