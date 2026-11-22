"""Authentication, session handling and role-based access control (all deterministic code)."""
from datetime import timedelta
import uuid
from sqlalchemy.orm import Session

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.db import SessionLocal, get_db, utcnow
from app.models import LoginThrottle, RevokedToken

COOKIE_NAME = "ff_session"

ROLE_RANK = {"requester": 0, "auditor": 0, "approver": 1, "manager": 2, "admin": 3}

_READ = {"dashboard:read", "workflows:read", "policies:read", "vendors:read", "integrations:read"}
PERMISSIONS = {
    "requester": _READ | {"requests:create"},
    "auditor": _READ | {"approvals:read", "exceptions:read", "audit:read"},
    "approver": _READ | {"requests:create", "approvals:read", "approvals:decide", "exceptions:read", "audit:read"},
    "manager": _READ
    | {"requests:create", "approvals:read", "approvals:decide", "exceptions:read", "audit:read", "workflows:operate", "vendors:write"},
    "admin": {"*"},
}


ALL_PERMISSIONS = set().union(*[v for v in PERMISSIONS.values() if "*" not in v]) | {"policies:write", "integrations:manage"}


def has_permission(role: str, permission: str) -> bool:
    perms = PERMISSIONS.get(role, set())
    return "*" in perms or permission in perms


def role_at_least(role: str, required: str) -> bool:
    return ROLE_RANK.get(role, -1) >= ROLE_RANK.get(required, 99)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=settings.bcrypt_rounds)).decode()


def verify_password(password: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode(), hashed.encode())
    except ValueError:
        return False


def create_token(user_id: int, role: str) -> str:
    exp = utcnow() + timedelta(hours=settings.session_hours)
    return jwt.encode({"sub": str(user_id), "role": role, "exp": exp, "jti": uuid.uuid4().hex}, settings.secret_key, algorithm="HS256")


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except jwt.PyJWTError:
        return None


def _extract_token(request: Request) -> str | None:
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        return auth[7:].strip()
    return request.cookies.get(COOKIE_NAME)


def get_current_user(request: Request, db: Session = Depends(get_db)):
    from app.models import User

    token = _extract_token(request)
    payload = decode_token(token) if token else None
    if not payload or not payload.get("jti"):
        raise HTTPException(status_code=401, detail="Authentication required. Please sign in again.")
    if db.query(RevokedToken).filter(RevokedToken.jti == payload["jti"]).first():
        raise HTTPException(status_code=401, detail="This session has been revoked. Please sign in again.")
    try:
        user = db.get(User, int(payload["sub"]))
    except (KeyError, TypeError, ValueError):
        user = None
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="This account is unavailable.")
    return user


def require(permission: str):
    def dependency(user=Depends(get_current_user)):
        if not has_permission(user.role, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Your role ({user.role}) is not permitted to perform this action ({permission}).",
            )
        return user

    return dependency


# --- login throttling --------------------------------------------------------------
# Throttle buckets are persisted in Postgres/SQLite so limits apply consistently across
# workers and restarts. Each bucket is keyed by normalized account or source IP.
IP_FAILURE_LIMIT = 40
THROTTLE_MESSAGE = "Too many sign-in attempts. Try again in a few minutes."


def normalise_email(email: str) -> str:
    return email.strip().lower()


def _bucket(db: Session, key: str) -> LoginThrottle:
    row = db.query(LoginThrottle).filter(LoginThrottle.bucket_key == key).with_for_update().first()
    if row is None:
        row = LoginThrottle(bucket_key=key, attempts=0, window_started_at=utcnow())
        db.add(row)
        db.flush()
    return row


def _in_window(row: LoginThrottle, window: int) -> bool:
    started = row.window_started_at
    if started.tzinfo is None:
        started = started.replace(tzinfo=utcnow().tzinfo)
    return (utcnow() - started).total_seconds() < window


def throttle_login(db: Session, key: str, limit: int = 8, window: int = 300) -> None:
    row = _bucket(db, f"account:{key}")
    if not _in_window(row, window):
        row.attempts = 0
        row.window_started_at = utcnow()
    if row.attempts >= limit:
        db.rollback()
        raise HTTPException(status_code=429, detail=THROTTLE_MESSAGE)
    row.attempts += 1
    db.commit()


def clear_throttle(db: Session, key: str) -> None:
    db.query(LoginThrottle).filter(LoginThrottle.bucket_key == f"account:{key}").delete(synchronize_session=False)
    db.commit()


def check_ip_throttle(db: Session, ip: str, limit: int = IP_FAILURE_LIMIT, window: int = 300) -> None:
    row = db.query(LoginThrottle).filter(LoginThrottle.bucket_key == f"ip:{ip}").first()
    if row is not None and _in_window(row, window) and row.attempts >= limit:
        raise HTTPException(status_code=429, detail=THROTTLE_MESSAGE)


def record_ip_failure(db: Session, ip: str, window: int = 300) -> None:
    row = _bucket(db, f"ip:{ip}")
    if not _in_window(row, window):
        row.attempts = 0
        row.window_started_at = utcnow()
    row.attempts += 1
    db.commit()


def reset_throttles() -> None:
    """Clear persisted throttle state (used by the test-suite)."""
    db = SessionLocal()
    try:
        db.query(LoginThrottle).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
