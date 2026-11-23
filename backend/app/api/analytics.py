from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api.workflows import _visible
from app.core.db import get_db
from app.core.security import require
from app.services import analytics

router = APIRouter(tags=["analytics"])


@router.get("/analytics/overview")
def overview(days: int = Query(30, ge=1, le=365), function: str | None = Query(None, max_length=50),
             db: Session = Depends(get_db), user=Depends(require("dashboard:read"))):
    if user.role == "requester":
        raise HTTPException(403, "Analytics are not available to requesters.")
    return analytics.overview(db, user.org_id, days, function)


@router.get("/workflows/{wid}/cost")
def workflow_cost(wid: int, db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    return analytics.workflow_cost(db, _visible(db, user, wid))
