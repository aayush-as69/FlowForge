"""Workflow + exception engines, driven through the reusable engine with a toy definition and the real procurement flow."""
import pytest

from app.exceptions import engine as exc_engine
from app.exceptions.engine import ExceptionSpec, ResolverResult
from app.models import Approval, Policy, PurchaseOrder, Workflow, WorkflowException
from app.services import approvals
from app.services import requests as rs
from app.workflows import engine, registry
from app.workflows.types import ApprovalSpec, FlowException, StepDef, StepResult, WorkflowDefinition

CALLS = {"flaky": 0, "resolver": 0}


def ok(sctx):
    return StepResult(output={"step": sctx.step.key})


def flaky(sctx):
    CALLS["flaky"] += 1
    if CALLS["flaky"] < 3:
        raise FlowException("TOY_TRANSIENT", "temporary glitch")
    return StepResult(output={"calls": CALLS["flaky"]})


def needs_resolver(sctx):
    if not sctx.overrides.get("fixed"):
        raise FlowException("TOY_FIXABLE", "needs fixing")
    return StepResult(output={"fixed": True})


def hopeless(sctx):
    if not sctx.overrides.get("human_ok"):
        raise FlowException("TOY_HUMAN", "cannot decide alone")
    return StepResult(output={"human": True})


def crash(sctx):
    raise ValueError("boom")


def approve_step(sctx):
    if sctx.ctx.get("grant"):
        return StepResult(status="skipped", reason="already approved")
    return StepResult(status="wait_human", approval=ApprovalSpec("t", "s", "r", "rec", assigned_role="approver"))


exc_engine.register(ExceptionSpec("TOY_TRANSIENT", "system", max_retries=2))
exc_engine.register(ExceptionSpec("TOY_FIXABLE", "system", resolvers=[
    lambda sctx, fe: ResolverResult(True, "fixed it", patch={"overrides": {"fixed": True}})]))
exc_engine.REGISTRY["TOY_FIXABLE"].resolvers[0].__name__ = "toy_fix"
exc_engine.register(ExceptionSpec("TOY_HUMAN", "system", on_approve=lambda d: {"human_ok": True}, review_role="approver"))


def toy(*steps):
    defn = WorkflowDefinition(key="toy", function_key="toy", name="Toy", steps=[StepDef(k, k, h) for k, h in steps])
    registry.register(defn)
    return defn


def make(db, users, defn):
    return engine.create_workflow(db, defn, org_id=1, title="toy", context={})


def statuses(db, wf):
    return {s.key: s.status for s in engine.steps_of(db, wf)}


def test_state_transitions_and_completion(db, users):
    wf = make(db, users, toy(("a", ok), ("b", ok), ("c", ok)))
    assert wf.status == "pending" and set(statuses(db, wf).values()) == {"pending"}
    engine.run(db, wf.id)
    db.refresh(wf)
    assert wf.status == "completed" and wf.completed_at and set(statuses(db, wf).values()) == {"completed"}


def test_recoverable_exception_retries_then_resolves(db, users):
    CALLS["flaky"] = 0
    wf = make(db, users, toy(("a", ok), ("b", flaky), ("c", ok)))
    engine.run(db, wf.id)
    db.refresh(wf)
    assert wf.status == "completed" and CALLS["flaky"] == 3
    exc = db.query(WorkflowException).filter_by(workflow_id=wf.id).all()
    assert len(exc) == 1 and exc[0].status == "auto_resolved" and exc[0].attempts == 2
    assert statuses(db, wf)["b"] == "resolved"


def test_auto_resolution_via_resolver(db, users):
    wf = make(db, users, toy(("a", needs_resolver), ("b", ok)))
    engine.run(db, wf.id)
    db.refresh(wf)
    exc = db.query(WorkflowException).filter_by(workflow_id=wf.id).one()
    assert wf.status == "completed" and exc.status == "auto_resolved" and exc.resolution == "fixed it"
    assert exc.resolution_trace[0]["ok"] is True


def test_retries_exhausted_escalates_to_human_then_workflow_resumes(db, users):
    CALLS["flaky"] = -10  # never succeeds within the retry budget
    wf = make(db, users, toy(("a", ok), ("b", flaky), ("c", ok)))
    engine.run(db, wf.id)
    db.refresh(wf)
    assert wf.status == "waiting_human" and statuses(db, wf)["b"] == "waiting_human"
    exc = db.query(WorkflowException).filter_by(workflow_id=wf.id, status="awaiting_review").one()
    approval = db.query(Approval).filter_by(workflow_id=wf.id).one()
    assert approval.exception_id == exc.id and approval.kind == "exception_review"
    CALLS["flaky"] = 5  # underlying problem fixed
    assert approvals.decide(db, approval, users["approver"], "approve", "go ahead", None) is True
    engine.run(db, wf.id)
    db.refresh(wf)
    assert wf.status == "completed"
    assert db.get(WorkflowException, exc.id).status == "resolved_by_human"


def test_human_review_modify_reject_and_escalate(db, users):
    wf = make(db, users, toy(("a", hopeless), ("b", ok)))
    engine.run(db, wf.id)
    approval = db.query(Approval).filter_by(workflow_id=wf.id).one()
    with pytest.raises(approvals.ApprovalError):  # requester role cannot decide
        approvals.decide(db, approval, users["requester"], "approve", None, None)
    approvals.decide(db, approval, users["approver"], "escalate", "needs more authority", None)
    db.refresh(approval)
    assert approval.assigned_role == "manager" and approval.escalated
    assert db.query(WorkflowException).filter_by(workflow_id=wf.id).one().status == "escalated"
    with pytest.raises(approvals.ApprovalError):  # approver no longer has enough authority
        approvals.decide(db, approval, users["approver"], "approve", None, None)
    approvals.decide(db, approval, users["manager"], "reject", "not acceptable", None)
    db.refresh(wf)
    assert wf.status == "cancelled" and statuses(db, wf)["b"] == "skipped"


def test_unrecoverable_exception_fails_and_operator_retry_resumes(db, users):
    state = {"n": 0}

    def once_bad(sctx):
        state["n"] += 1
        if state["n"] == 1:
            raise ValueError("boom")
        return StepResult()

    wf = make(db, users, toy(("a", once_bad), ("b", ok)))
    engine.run(db, wf.id)
    db.refresh(wf)
    exc = db.query(WorkflowException).filter_by(workflow_id=wf.id).one()
    assert wf.status == "failed" and exc.status == "failed" and not exc.recoverable and "boom" in wf.error
    engine.retry_failed(db, wf, "Aarav")
    engine.run(db, wf.id)
    db.refresh(wf)
    assert wf.status == "completed"


def test_interruption_and_resumption_is_idempotent(db, users):
    wf = make(db, users, toy(("a", ok), ("b", ok), ("c", ok)))
    first = engine.steps_of(db, wf)[0]
    first.status, wf.status, wf.started_at = "completed", "running", wf.created_at  # simulate a crash after step a
    db.commit()
    engine.run(db, wf.id)
    db.refresh(wf)
    steps = engine.steps_of(db, wf)
    assert wf.status == "completed" and steps[0].attempts == 0 and all(s.status == "completed" for s in steps)
    engine.run(db, wf.id)  # running a finished workflow is a no-op
    assert db.get(Workflow, wf.id).status == "completed"


# ------------------------------------------------------------------ full procurement flow
def run_request(db, users, text, faults=None, requester="requester"):
    req = rs.create_request(db, users[requester], text=text, fields=None, source="text", demo_faults=faults or [])
    wf = rs.start_workflow(db, req, users[requester], step_delay=0)
    engine.run(db, wf.id)
    db.refresh(wf)
    return wf


def pending(db, wf):
    return db.query(Approval).filter_by(workflow_id=wf.id, status="pending").first()


def test_primary_demo_end_to_end(db, users):
    wf = run_request(db, users, "Purchase a laptop for a new employee joining next Monday. Budget ₹1,00,000.", ["erp_timeout"])
    # 1) price anomaly cannot be auto-resolved -> human review of the exception
    assert wf.status == "waiting_human" and wf.current_step_key == "vendor_evaluation"
    a1 = pending(db, wf)
    assert a1.kind == "exception_review" and "18.0%" in a1.title and a1.assigned_role == "approver"
    assert a1.supporting_data["alternatives_rejected"] and "Apex" in a1.reason
    approvals.decide(db, a1, users["approver"], "approve", "Only vendor that meets delivery and reliability", None)
    engine.run(db, wf.id)
    db.refresh(wf)
    # 2) manager approval required by policy
    a2 = pending(db, wf)
    assert wf.status == "waiting_human" and a2.kind == "approval" and a2.assigned_role == "manager" and a2.level == 2
    approvals.decide(db, a2, users["manager"], "approve", None, None)
    engine.run(db, wf.id)
    db.refresh(wf)
    # 3) execution incl. ERP timeout retried automatically
    assert wf.status == "completed", wf.error
    po = db.query(PurchaseOrder).filter_by(workflow_id=wf.id).one()
    assert po.vendor.name == "Bluepeak Systems" and po.total == 91_000 and po.erp_ref and po.accounting_ref
    excs = {e.code: e for e in db.query(WorkflowException).filter_by(workflow_id=wf.id)}
    assert excs["PRICE_ANOMALY"].status == "resolved_by_human" and excs["INTEGRATION_TIMEOUT"].status == "auto_resolved"
    st = statuses(db, wf)
    assert st["vendor_evaluation"] == "resolved" and st["erp_update"] == "resolved" and st["complete"] == "completed"
    assert wf.outcome_data["human_decisions"] == 2


def test_routine_purchase_is_fully_autonomous(db, users):
    wf = run_request(db, users, "Need 5 wireless keyboard and mouse sets for the support team. Budget ₹20,000. Needed by next Friday.")
    assert wf.status == "completed" and db.query(Approval).filter_by(workflow_id=wf.id).count() == 0
    assert statuses(db, wf)["approval"] == "skipped"


def test_vendor_unavailable_recovers_with_alternative_and_recalculation(db, users):
    wf = run_request(db, users, "Need 4 27-inch monitors for the platform team. Budget ₹1,40,000. Required by next Thursday.", ["vendor_unavailable"])
    a = pending(db, wf)
    if a is not None:  # manager approval for >₹50k; existing approval must cover the substituted vendor
        approvals.decide(db, a, users["manager"], "approve", None, None)
        engine.run(db, wf.id)
        db.refresh(wf)
    exc = db.query(WorkflowException).filter_by(workflow_id=wf.id, code="VENDOR_UNAVAILABLE").one()
    assert exc.status == "auto_resolved" and "alternative" in exc.resolution.lower()
    assert wf.status in ("completed", "waiting_human"), wf.error
    if wf.status == "waiting_human":
        assert pending(db, wf).kind == "approval"


def test_policy_block_requires_admin_override(db, users):
    wf = run_request(db, users, "Need a rack server for the data room. Budget ₹4,50,000. Required by next Friday.")
    a = pending(db, wf)
    assert wf.status == "waiting_human" and a.assigned_role == "admin" and a.level == 3
    with pytest.raises(approvals.ApprovalError):
        approvals.decide(db, a, users["manager"], "approve", "x", None)
    approvals.decide(db, a, users["admin"], "reject", "Servers go through formal tender", None)
    db.refresh(wf)
    assert wf.status == "cancelled"


def test_level3_requires_justification_and_changed_policy_changes_decision(db, users):
    wf = run_request(db, users, "Purchase 4 network switches for the Pune office. Budget ₹3,80,000. Required by next Friday.")
    a = pending(db, wf)
    assert a.level == 3 and a.assigned_role == "admin"
    with pytest.raises(approvals.ApprovalError) as err:
        approvals.decide(db, a, users["admin"], "approve", "", None)
    assert err.value.status == 422
    # administrators raise the autonomy limits: the same request now runs without a human
    for p in db.query(Policy).filter(Policy.rule_type.in_(["auto_execute_limit", "human_decision_limit", "approval_threshold"])):
        p.params = {**p.params, **({"max_amount": 10**7} if p.rule_type == "auto_execute_limit" else
                                   {"min_amount": 10**8} if p.rule_type == "human_decision_limit" else {"amount": 10**8})}
    db.commit()
    wf2 = run_request(db, users, "Purchase 4 network switches for the Pune office. Budget ₹3,80,000. Required by next Friday.")
    assert wf2.status == "completed" and db.query(Approval).filter_by(workflow_id=wf2.id).count() == 0


def test_permission_boundary_blocks_destructive_tool(db, users):
    def sneaky(sctx):
        sctx.tool("accounting.release_payment", po_number="PO-1")
        return StepResult()

    wf = make(db, users, toy(("a", sneaky)))
    wf.step_delay = 0
    engine.run(db, wf.id)
    db.refresh(wf)
    exc = db.query(WorkflowException).filter_by(workflow_id=wf.id).one()
    assert wf.status == "failed" and exc.code == "PERMISSION_BOUNDARY"
