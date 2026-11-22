from datetime import datetime, timezone

from sqlalchemy import MetaData, create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import settings

# All FlowForge tables live in their own Postgres schema so they never collide with other tooling.
SCHEMA = "flowforge"


class Base(DeclarativeBase):
    metadata = MetaData(schema=SCHEMA)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def make_engine(url: str):
    if url.startswith("sqlite"):
        engine = create_engine(
            url, connect_args={"check_same_thread": False}, poolclass=StaticPool
        )
        return engine.execution_options(schema_translate_map={SCHEMA: None})
    return create_engine(url, pool_pre_ping=True, pool_size=10, max_overflow=20)


engine = make_engine(settings.database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)


def configure(url: str) -> None:
    """Re-point the module at another database (used by the test-suite)."""
    global engine
    engine = make_engine(url)
    SessionLocal.configure(bind=engine)


def init_db() -> None:
    from app import models  # noqa: F401  (register tables)

    if not str(engine.url).startswith("sqlite"):
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{SCHEMA}"'))
    Base.metadata.create_all(engine)
    _install_audit_immutability()


def _install_audit_immutability() -> None:
    """Install database-level guards so audit history cannot be edited or deleted."""
    if str(engine.url).startswith("sqlite"):
        with engine.begin() as conn:
            conn.execute(text("""
                CREATE TRIGGER IF NOT EXISTS audit_events_immutable_update
                BEFORE UPDATE ON audit_events
                BEGIN SELECT RAISE(ABORT, 'audit_events are immutable'); END;
            """))
            conn.execute(text("""
                CREATE TRIGGER IF NOT EXISTS audit_events_immutable_delete
                BEFORE DELETE ON audit_events
                BEGIN SELECT RAISE(ABORT, 'audit_events are immutable'); END;
            """))
        return
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE OR REPLACE FUNCTION flowforge.prevent_audit_mutation()
            RETURNS trigger LANGUAGE plpgsql AS $$
            BEGIN
                RAISE EXCEPTION 'audit_events are immutable';
            END;
            $$;
        """))
        conn.execute(text("""
            DROP TRIGGER IF EXISTS audit_events_immutable ON flowforge.audit_events;
            CREATE TRIGGER audit_events_immutable
            BEFORE UPDATE OR DELETE ON flowforge.audit_events
            FOR EACH ROW EXECUTE FUNCTION flowforge.prevent_audit_mutation();
        """))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
