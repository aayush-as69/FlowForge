"""Workflow Builder: validate, interpret, dry-run and test user-built workflows.

A custom workflow is *data* (an ordered list of typed steps), never code. Each step type maps to a small, audited,
deterministic handler built on the same engine, approvals and exception machinery the procurement workflow uses.
Supported step types:

  extract   understand the request text into fields (item, quantity, amount, category, …)
  rule      check conditions on those fields; on failure either flag the case for approval or block it for review
  approval  ask a person with at least the given role (always, or only when an earlier rule flagged the case)
  notify    record a notification (audit-logged; no external system is contacted)

Limits worth knowing: steps run in order (no parallel branches or timers) and "notify" does not send real messages.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from app.agents import extraction
from app.exceptions import engine as exception_engine
from app.exceptions.engine import ExceptionSpec
from app.workflows.types import ApprovalSpec, FlowException, StepContext, StepDef, StepResult, WorkflowDefinition

STEP_TYPES = {"extract": "Understand request", "rule": "Policy check", "approval": "Human approval", "notify": "Notify"}
OPS = {"<", "<=", ">", ">=", "==", "!=", "in", "contains", "exists"}
FIELDS = ("item", "category", "quantity", "amount", "purpose", "required_date_text", "requirements", "text")
NUMERIC_FIELDS = {"quantity", "amount"}
ROLES = ("approver", "manager", "admin")
MAX_STEPS = 20
ID_RE = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
KEY_RE = re.compile(r"^[a-z][a-z0-9-]{1,59}$")


class SpecError(ValueError):
    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


# ----------------------------------------------------------------------------- validation
def _condition_problems(where: str, c: Any) -> list[str]:
    if not isinstance(c, dict):
        return [f"{where}: condition must be an object"]
    out = []
    field, op, value = c.get("field"), c.get("op"), c.get("value")
    if field not in FIELDS:
        out.append(f"{where}: unknown field '{field}' (use one of {', '.join(FIELDS)})")
    if op not in OPS:
        out.append(f"{where}: unknown operator '{op}'")
        return out
    if op in ("<", "<=", ">", ">="):
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            out.append(f"{where}: '{op}' needs a number")
        elif field not in NUMERIC_FIELDS:
            out.append(f"{where}: '{op}' only works on numeric fields (quantity, amount)")
    elif op == "in":
        if not isinstance(value, list) or not value or len(value) > 50:
            out.append(f"{where}: 'in' needs a non-empty list (max 50)")
    elif op == "contains":
        if not isinstance(value, str) or not value:
            out.append(f"{where}: 'contains' needs text")
    elif op in ("==", "!=") and (isinstance(value, (dict, list)) or value is None):
        out.append(f"{where}: '{op}' needs a number or text")
    return out


def validate_spec(spec: Any) -> list[str]:
    """Return every problem found (empty list = valid). Never raises, so the UI can show all of them at once."""
    if not isinstance(spec, dict) or not isinstance(spec.get("steps"), list):
        return ["spec must be an object with a 'steps' list"]
    steps = spec["steps"]
    if not steps:
        return ["add at least one step"]
    if len(steps) > MAX_STEPS:
        return [f"a workflow can have at most {MAX_STEPS} steps"]
    problems: list[str] = []
    seen: set[str] = set()
    flagged_before = False
    extracted = False
    for i, s in enumerate(steps, 1):
        where = f"step {i}"
        if not isinstance(s, dict):
            problems.append(f"{where}: must be an object")
            continue
        sid, kind = s.get("id"), s.get("type")
        if not isinstance(sid, str) or not ID_RE.match(sid):
            problems.append(f"{where}: id must be lowercase letters, digits or _ (start with a letter)")
        elif sid in seen:
            problems.append(f"{where}: duplicate id '{sid}'")
        else:
            seen.add(sid)
        if kind not in STEP_TYPES:
            problems.append(f"{where}: unknown type '{kind}'")
            continue
        name = s.get("name")
        if not isinstance(name, str) or not name.strip() or len(name) > 100:
            problems.append(f"{where}: needs a name (max 100 characters)")
        where = f"step {i} ({name or sid})"
        if kind == "extract":
            extracted = True
        elif kind == "rule":
            conds = s.get("conditions")
            if not isinstance(conds, list) or not conds or len(conds) > 10:
                problems.append(f"{where}: add 1–10 conditions")
            else:
                for c in conds:
                    problems += _condition_problems(where, c)
            if s.get("on_fail") not in ("approval", "block"):
                problems.append(f"{where}: on_fail must be 'approval' or 'block'")
            if s.get("on_fail") == "approval":
                flagged_before = True
            if not isinstance(s.get("message", ""), str) or len(s.get("message", "")) > 300:
                problems.append(f"{where}: message must be text (max 300 characters)")
        elif kind == "approval":
            if s.get("role") not in ROLES:
                problems.append(f"{where}: role must be one of {', '.join(ROLES)}")
            when = s.get("when", "always")
            if when not in ("always", "flagged"):
                problems.append(f"{where}: when must be 'always' or 'flagged'")
            elif when == "flagged" and not flagged_before:
                problems.append(f"{where}: 'flagged' needs an earlier rule step that flags for approval")
        elif kind == "notify":
            msg = s.get("message")
            if not isinstance(msg, str) or not msg.strip() or len(msg) > 300:
                problems.append(f"{where}: needs a message (max 300 characters)")
    if steps and not problems:
        if not extracted:
            problems.append("add an 'extract' step so rules have fields to check")
        elif steps[0].get("type") != "extract":
            problems.append("the first step must be 'extract'")
        elif sum(1 for s in steps if s.get("type") == "extract") > 1:
            problems.append("only one 'extract' step is allowed")
    return problems


def validate_tests(tests: Any) -> list[str]:
    if tests is None:
        return []
    if not isinstance(tests, list) or len(tests) > 50:
        return ["tests must be a list of at most 50 cases"]
    out = []
    for i, t in enumerate(tests, 1):
        if not isinstance(t, dict) or not isinstance(t.get("name"), str) or not t["name"].strip():
            out.append(f"test {i}: needs a name")
            continue
        if not (isinstance(t.get("text"), str) and t["text"].strip()) and not isinstance(t.get("fields"), dict):
            out.append(f"test {i}: needs 'text' or 'fields'")
        exp = t.get("expect")
        if not isinstance(exp, dict) or exp.get("outcome") not in ("auto", "approval", "blocked"):
            out.append(f"test {i}: expect.outcome must be 'auto', 'approval' or 'blocked'")
        elif exp.get("role") is not None and exp["role"] not in ROLES:
            out.append(f"test {i}: expect.role must be one of {', '.join(ROLES)}")
    return out


# ----------------------------------------------------------------------------- field extraction & rules
def extract_fields(text: str | None, provided: dict | None = None, today: date | None = None) -> dict:
    """Heuristic extraction (deterministic) with structured input always winning over inferred values."""
    fields: dict[str, Any] = {"text": (text or "").strip()}
    if fields["text"]:
        res = extraction.heuristic_extract(fields["text"], today).fields
        fields.update(item=res.item, category=res.category, quantity=res.quantity, amount=res.budget,
                      purpose=res.purpose, required_date_text=res.required_date_text, requirements=res.requirements)
    for key, value in (provided or {}).items():
        if key in FIELDS and value not in (None, ""):
            fields[key] = value
    return {k: v for k, v in fields.items() if v not in (None, "")}


def _num(v):
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return v
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def check_condition(c: dict, fields: dict) -> tuple[bool, str]:
    field, op, want = c["field"], c["op"], c.get("value")
    have = fields.get(field)
    if op == "exists":
        return have is not None, f"{field} is {'present' if have is not None else 'missing'}"
    if have is None:
        return False, f"{field} was not found in the request"
    if op in ("<", "<=", ">", ">="):
        n = _num(have)
        if n is None:
            return False, f"{field} '{have}' is not a number"
        ok = {"<": n < want, "<=": n <= want, ">": n > want, ">=": n >= want}[op]
        return ok, f"{field} {n:g} {'satisfies' if ok else 'does not satisfy'} {op} {want:g}"
    if op == "in":
        ok = str(have).lower() in {str(x).lower() for x in want}
        return ok, f"{field} '{have}' {'is' if ok else 'is not'} one of {', '.join(map(str, want))}"
    if op == "contains":
        ok = want.lower() in str(have).lower()
        return ok, f"{field} {'contains' if ok else 'does not contain'} '{want}'"
    same = (_num(have) == _num(want)) if _num(have) is not None and _num(want) is not None else str(have).lower() == str(want).lower()
    ok = same if op == "==" else not same
    return ok, f"{field} '{have}' {'matches' if ok else 'does not match'} {op} '{want}'"


def evaluate_rule(step: dict, fields: dict) -> dict:
    checks = []
    for c in step["conditions"]:
        ok, why = check_condition(c, fields)
        checks.append({"ok": ok, "text": why})
    passed = all(c["ok"] for c in checks)
    return {"passed": passed, "checks": checks}


def _render(message: str, fields: dict) -> str:
    return re.sub(r"\{(\w+)\}", lambda m: str(fields.get(m.group(1), "—")) if m.group(1) in FIELDS else m.group(0), message)


# ----------------------------------------------------------------------------- dry run (test mode)
def dry_run(spec: dict, text: str | None = None, fields: dict | None = None, today: date | None = None) -> dict:
    """Walk the spec exactly as the engine would, without touching the database or any person."""
    problems = validate_spec(spec)
    if problems:
        raise SpecError(problems)
    f = extract_fields(text, fields, today)
    flags: list[str] = []
    trace: list[dict] = []
    outcome, role = "auto", None
    for s in spec["steps"]:
        row = {"id": s["id"], "name": s["name"], "type": s["type"]}
        kind = s["type"]
        if kind == "extract":
            row.update(result="ok", detail=f"{len(f)} field(s): " + (", ".join(f"{k}={v}" for k, v in f.items() if k != "text") or "none"))
        elif kind == "rule":
            r = evaluate_rule(s, f)
            row.update(checks=r["checks"])
            if r["passed"]:
                row.update(result="passed", detail="All conditions satisfied")
            elif s["on_fail"] == "block":
                row.update(result="blocked", detail=s.get("message") or "Rule failed")
                trace.append(row)
                outcome = "blocked"
                break
            else:
                flags.append(s["id"])
                row.update(result="flagged", detail=s.get("message") or "Rule failed — approval required")
        elif kind == "approval":
            needed = s.get("when", "always") == "always" or bool(flags)
            if needed:
                row.update(result="approval", detail=f"Waits for {s['role']}")
                outcome = "approval"
                if role is None or ROLES.index(s["role"]) > ROLES.index(role):
                    role = s["role"]
            else:
                row.update(result="skipped", detail="No rule flagged this case")
        elif kind == "notify":
            row.update(result="notified", detail=_render(s["message"], f))
        trace.append(row)
    return {"outcome": outcome, "role": role, "fields": f, "trace": trace}


def run_tests(spec: dict, tests: list[dict], today: date | None = None) -> dict:
    results = []
    for t in tests or []:
        try:
            r = dry_run(spec, t.get("text"), t.get("fields"), today)
            exp = t["expect"]
            ok = r["outcome"] == exp["outcome"] and (exp.get("role") is None or exp["role"] == r["role"])
            got = r["outcome"] + (f" ({r['role']})" if r["role"] else "")
        except SpecError as e:
            ok, got = False, f"invalid workflow: {e}"
        exp = t["expect"]
        want = exp["outcome"] + (f" ({exp['role']})" if exp.get("role") else "")
        results.append({"name": t["name"], "passed": ok, "expected": want, "actual": got})
    passed = sum(1 for r in results if r["passed"])
    return {"total": len(results), "passed": passed, "failed": len(results) - passed, "results": results}


# ----------------------------------------------------------------------------- real execution
exception_engine.register(ExceptionSpec(
    "RULE_BLOCKED", "policy", "A workflow rule blocked this request", severity="medium", recoverable=True,
    human_review=True, review_role="manager",
    on_approve=lambda d: {f"waive:{d.get('step_key')}": True},
))


def _handlers(step: dict):
    kind = step["type"]

    def extract(sctx: StepContext) -> StepResult:
        inp = sctx.ctx.get("input") or {}
        f = extract_fields(inp.get("text"), inp.get("fields"))
        return StepResult(output={"fields": f}, decision=f"{len(f)} field(s) understood", ctx_patch={"fields": f})

    def rule(sctx: StepContext) -> StepResult:
        f = sctx.ctx.get("fields", {})
        r = evaluate_rule(step, f)
        if r["passed"]:
            return StepResult(output=r, decision="Passed", reason="All conditions satisfied")
        msg = step.get("message") or "Rule failed"
        if sctx.overrides.get(f"waive:{step['id']}"):
            return StepResult(output={**r, "waived": True}, decision="Waived by a reviewer", reason=msg)
        if step["on_fail"] == "block":
            raise FlowException("RULE_BLOCKED", msg, {"step_key": step["id"], "checks": r["checks"]})
        flags = [*sctx.ctx.get("flags", []), {"step": step["id"], "message": msg}]
        return StepResult(output=r, decision="Flagged for approval", reason=msg, ctx_patch={"flags": flags})

    def approval(sctx: StepContext) -> StepResult:
        ctx = sctx.ctx
        flags = ctx.get("flags", [])
        if step.get("when", "always") == "flagged" and not flags:
            return StepResult(status="skipped", decision="Not required", reason="No rule flagged this case")
        f = ctx.get("fields", {})
        why = "; ".join(x["message"] for x in flags) or "This workflow requires a sign-off"
        spec = ApprovalSpec(
            title=f"{step['name']}: {sctx.workflow.title}",
            summary=f"{sctx.workflow.title}" + (f" — amount {f['amount']:,}" if isinstance(f.get("amount"), (int, float)) else ""),
            reason=why, recommendation="Review the request and the rule results, then decide.",
            risk="Workflow is paused until a decision is made.", risk_level="medium",
            supporting_data={"fields": f, "flags": flags}, assigned_role=step["role"], level=2)
        return StepResult(status="wait_human", approval=spec, output={"requested_role": step["role"]},
                          decision=f"Waiting for {step['role']}", reason=why)

    def notify(sctx: StepContext) -> StepResult:
        text = _render(step["message"], sctx.ctx.get("fields", {}))
        sctx.audit("notification.recorded", actor_type="system", actor="FlowForge Workflow", output={"message": text},
                   result="ok", reason="Notification recorded (not sent externally)")
        return StepResult(output={"message": text}, decision="Recorded", reason=text,
                          ctx_patch={"notifications": [*sctx.ctx.get("notifications", []), text]})

    return {"extract": extract, "rule": rule, "approval": approval, "notify": notify}[kind]


def build_definition(record) -> WorkflowDefinition:
    spec = record.spec
    steps = [StepDef(key=s["id"], name=s["name"], handler=_handlers(s),
                     kind={"extract": "automated", "rule": "decision", "approval": "approval", "notify": "automated"}[s["type"]],
                     action=STEP_TYPES[s["type"]]) for s in spec["steps"]]

    def criteria(db, wf):
        wf.outcome = f"Completed '{record.name}' v{record.version}"
        return []

    return WorkflowDefinition(key=f"custom:{record.id}", function_key="custom", name=f"{record.name} v{record.version}",
                              steps=steps, completion_criteria=criteria)
