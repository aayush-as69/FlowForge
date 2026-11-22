from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from app.api.serializers import ser_user
from app.core.config import settings
from app.core.db import get_db
from app.core.security import (ALL_PERMISSIONS, COOKIE_NAME, PERMISSIONS, check_ip_throttle, clear_throttle, create_token,
                               decode_token, get_current_user, normalise_email, record_ip_failure, throttle_login, verify_password, _extract_token)
from app.models import RevokedToken, User
from app.schemas.api import LoginIn
from app.services import audit

router = APIRouter(prefix="/auth", tags=["auth"])


def _permissions(role: str) -> list[str]:
    perms = PERMISSIONS.get(role, set())
    if "*" in perms:
        return sorted(ALL_PERMISSIONS)
    return sorted(perms)


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = Depends(get_db)):
    ip = request.client.host if request.client else "unknown"
    email = normalise_email(body.email)  # the throttle key and the account lookup must use the very same spelling
    check_ip_throttle(db, ip)
    key = f"{ip}:{email}"
    throttle_login(db, key)
    user = db.query(User).filter(User.email == email).first()
    if not user or not user.is_active or not verify_password(body.password, user.password_hash):
        record_ip_failure(db, ip)
        audit.record(db, org_id=user.org_id if user else 1, workflow_id=None, actor_type="user", actor=email[:200],
                     action="auth.login_failed", result="denied", status="denied", reason="Invalid credentials")
        db.commit()
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    clear_throttle(db, key)
    response.set_cookie(COOKIE_NAME, create_token(user.id, user.role), httponly=True, samesite="lax",
                        secure=settings.cookie_secure, max_age=settings.session_hours * 3600, path="/")
    audit.record(db, org_id=user.org_id, workflow_id=None, actor_type="user", actor=user.name, action="auth.login", status="ok")
    db.commit()
    return {"user": ser_user(user), "permissions": _permissions(user.role)}


@router.post("/logout")
def logout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = _extract_token(request)
    payload = decode_token(token) if token else None
    if payload and payload.get("jti"):
        expires = payload.get("exp")
        if expires:
            db.merge(RevokedToken(jti=payload["jti"], expires_at=datetime.fromtimestamp(expires, tz=timezone.utc)))
            db.commit()
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/me")
def me(user: User = Depends(get_current_user)):
    return {"user": ser_user(user), "permissions": _permissions(user.role)}
