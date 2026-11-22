from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.api import serializers as ser
from app.core.db import get_db
from app.core.security import require
from app.models import Request, User
from app.schemas.api import DemoIn, RequestCreate, RequestUpdate
from app.services import requests as svc
from app.services import runner

router = APIRouter(tags=["requests"])

SCENARIOS = {
    "laptop_primary": {
        "label": "Laptop for a new joiner — price anomaly, human review, ERP retry",
        "text": "Purchase a laptop for a new employee joining next Monday. Budget ₹1,00,000.", "faults": ["erp_timeout"],
        "shows": ["AI extraction", "HR verification", "Vendor comparison", "Price anomaly → human review", "Manager approval", "ERP timeout auto-retry", "Audit trail"]},
    "vendor_outage": {
        "label": "Monitors — vendor outage recovered automatically",
        "text": "Need 4 27-inch monitors for the platform team. Budget ₹1,40,000. Required by next Thursday.", "faults": ["vendor_unavailable"],
        "shows": ["Vendor unavailable", "Alternative search", "Price recalculation", "Policy re-check", "Manager approval"]},
    "routine": {
        "label": "Keyboard & mouse sets — fully autonomous (Level 1)",
        "text": "Need 5 wireless keyboard and mouse sets for the support team. Budget ₹20,000. Needed by next Friday.", "faults": [],
        "shows": ["Zero human involvement", "Level 1 auto-execute"]},
    "high_value": {
        "label": "Network switches — Level 3 human decision",
        "text": "Purchase 4 network switches for the Pune office. Budget ₹3,80,000. Required by next Friday. Purpose: team expansion", "faults": [],
        "shows": ["High-impact threshold", "Executive accountability", "Written justification"]},
    "blocked_category": {
        "label": "Rack server — blocked by category policy",
        "text": "Need a rack server for the data room. Budget ₹4,50,000. Required by next Friday. Purpose: team expansion", "faults": [],
        "shows": ["Policy block", "Administrator override review"]},
}


def _own(db: Session, user, rid: int) -> Request:
    req = db.get(Request, rid)
    if req is None or req.org_id != user.org_id:
        raise HTTPException(404, "Request not found.")
    if user.role == "requester" and req.requester_id != user.id:
        raise HTTPException(403, "You can only access your own requests.")
    return req


@router.post("/requests", status_code=201)
def create(body: RequestCreate, db: Session = Depends(get_db), user=Depends(require("requests:create"))):
    fields = body.fields.model_dump() if body.fields else None
    req = svc.create_request(db, user, text=body.text, fields=fields, source=body.source, demo_faults=[])
    return ser.ser_request(req)


@router.get("/requests")
def list_requests(page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100), db: Session = Depends(get_db),
                  user=Depends(require("workflows:read"))):
    query = db.query(Request).filter(Request.org_id == user.org_id)
    if user.role == "requester":
        query = query.filter(Request.requester_id == user.id)
    total = query.count()
    rows = query.order_by(Request.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return ser.page([ser.ser_request(r) for r in rows], total, page, page_size)


@router.get("/requests/{rid}")
def get_request(rid: int, db: Session = Depends(get_db), user=Depends(require("workflows:read"))):
    return ser.ser_request(_own(db, user, rid))


@router.patch("/requests/{rid}")
def update(rid: int, body: RequestUpdate, db: Session = Depends(get_db), user=Depends(require("requests:create"))):
    req = _own(db, user, rid)
    if req.status != "extracted":
        raise HTTPException(409, "This request is already executing and can no longer be edited.")
    return ser.ser_request(svc.update_request(db, req, body.model_dump(exclude_unset=True), user))


@router.post("/requests/{rid}/execute", status_code=202)
def execute(rid: int, bg: BackgroundTasks, db: Session = Depends(get_db), user=Depends(require("requests:create"))):
    req = _own(db, user, rid)
    if req.status != "extracted":
        raise HTTPException(409, "This request has already been executed.")
    missing = svc.missing_fields(req)
    if missing:
        raise HTTPException(422, f"Please complete the missing information before execution: {', '.join(missing)}.")
    wf = svc.start_workflow(db, req, user)
    bg.add_task(runner.submit, wf.id)
    return {"workflow_id": wf.id, "ref": ser.wf_ref(wf.id)}


functions_router = APIRouter(prefix="/functions", tags=["functions"])


@functions_router.get("/procurement/scenarios")
def scenarios(user=Depends(require("workflows:read"))):
    return [{"key": k, **{kk: vv for kk, vv in v.items()}} for k, v in SCENARIOS.items()]


@functions_router.post("/procurement/demo", status_code=202)
def run_demo(body: DemoIn, bg: BackgroundTasks, db: Session = Depends(get_db), user=Depends(require("requests:create"))):
    sc = SCENARIOS[body.scenario]
    on_behalf = db.query(User).filter(User.email == "requester@flowforge.demo").first() or user
    req = svc.create_request(db, user, text=sc["text"], fields=None, source="text", demo_faults=sc["faults"], is_demo=True,
                             requester=on_behalf)
    wf = svc.start_workflow(db, req, user, is_demo=True)
    bg.add_task(runner.submit, wf.id)
    return {"workflow_id": wf.id, "ref": ser.wf_ref(wf.id), "requester": on_behalf.name}
