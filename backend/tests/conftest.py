import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
if os.path.isdir(os.path.join(HERE, ".pylibs")):
    sys.path.insert(0, os.path.join(HERE, ".pylibs"))

os.environ.update({
    "DATABASE_URL": "sqlite://", "FF_SYNC_RUNNER": "1", "FF_STEP_DELAY": "0", "FF_RETRY_BACKOFF": "0",
    "FF_SEED": "0", "DEMO_PASSWORD": "test-only-demo-password", "SECRET_KEY": "test-secret-key-not-for-production", "BCRYPT_ROUNDS": "4", "LLM_API_KEY": "",
})

import pytest  # noqa: E402

import app.workflows.procurement  # noqa: E402,F401
from app.core import db as database  # noqa: E402
from app.models import User  # noqa: E402
from app.services import seed  # noqa: E402


@pytest.fixture(autouse=True)
def _fresh_login_throttle():
    """Throttle counters live in process memory; never let one test's failed logins lock out the next test."""
    from app.core import security

    security.reset_throttles()
    yield


@pytest.fixture()
def db():
    database.Base.metadata.drop_all(database.engine)
    database.init_db()
    session = database.SessionLocal()
    seed.seed_base(session)
    yield session
    session.close()


@pytest.fixture()
def users(db):
    return {u.email.split("@")[0]: u for u in db.query(User).all()}
