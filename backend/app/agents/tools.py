"""Explicit tool/action definitions with permission boundaries.

The AI layer can only *request* actions that are registered here. Every call is checked against
(1) the tools allowed for the current workflow step, (2) the scopes granted to the function's agent, and
(3) a hard block on destructive tools unless a human explicitly approved them. Every call is audited."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Any, Callable

from app.integrations.adapters import IntegrationError, get_adapter
from app.models import ToolExecution
from app.workflows.types import FlowException


@dataclass
class ToolDef:
    name: str
    description: str
    scope: str
    integration: str
    handler: Callable[..., Any]
    destructive: bool = False


TOOLS: dict[str, ToolDef] = {}


def tool(name: str, description: str, scope: str, integration: str, destructive: bool = False):
    def deco(fn):
        TOOLS[name] = ToolDef(name, description, scope, integration, fn, destructive)
        return fn

    return deco


@tool("documents.store", "Store a document in enterprise document storage", "documents:write", "documents")
def _store(sctx, adapter, name, content, idempotency_key=None):
    return adapter.store(name, content, idempotency_key=idempotency_key)


@tool("crm.get_stakeholder", "Look up requester/department/cost centre", "crm:read", "crm")
def _crm(sctx, adapter, name, email, idempotency_key=None):
    return adapter.get_stakeholder(name, email)


@tool("hr.verify_new_hire", "Verify an employee requirement in the HR system", "hr:read", "hr")
def _hr(sctx, adapter, requester, purpose, idempotency_key=None):
    return adapter.verify_new_hire(requester, purpose)


@tool("vendors.search", "Search the vendor database for a category", "vendors:read", "vendor_db")
def _vsearch(sctx, adapter, category, idempotency_key=None):
    return adapter.search(sctx.workflow.org_id, category)


@tool("vendors.confirm_availability", "Confirm vendor stock/availability", "vendors:read", "vendor_db")
def _vavail(sctx, adapter, vendor_id, idempotency_key=None):
    return adapter.confirm_availability(vendor_id, simulate_outage=sctx.consume_fault("vendor_unavailable"))


@tool("vendors.confirm_order", "Send the purchase order to the vendor and obtain confirmation", "vendors:write", "vendor_db")
def _vorder(sctx, adapter, po_number, vendor_id, idempotency_key=None):
    return adapter.confirm_order(po_number, vendor_id, idempotency_key=idempotency_key)


@tool("accounting.check_budget", "Check budget availability for a cost centre", "accounting:read", "accounting")
def _acc_budget(sctx, adapter, amount, cost_center, idempotency_key=None):
    return adapter.check_budget(amount, cost_center)


@tool("accounting.reserve_commitment", "Post a budget commitment", "accounting:write", "accounting")
def _acc_commit(sctx, adapter, po_number, amount, idempotency_key=None):
    return adapter.reserve_commitment(po_number, amount, idempotency_key=idempotency_key)


@tool("accounting.match_invoice", "Three-way match invoice against PO", "accounting:read", "accounting")
def _acc_match(sctx, adapter, po_number, amount, idempotency_key=None):
    return adapter.match_invoice(po_number, amount, simulate_mismatch=sctx.consume_fault("invoice_mismatch"))


@tool("erp.create_purchase_order", "Create a purchase order in the ERP", "erp:write", "erp")
def _erp(sctx, adapter, po, idempotency_key=None):
    return adapter.create_purchase_order(po, simulate_timeout=sctx.consume_fault("erp_timeout"), idempotency_key=idempotency_key)


@tool("email.send", "Send a notification email", "email:send", "email")
def _email(sctx, adapter, to, subject, body, idempotency_key=None):
    return adapter.send(to, subject, body, idempotency_key=idempotency_key)


@tool("accounting.release_payment", "Release a payment (destructive)", "payments:release", "accounting", destructive=True)
def _pay(sctx, adapter, po_number, idempotency_key=None):
    return adapter.release_payment(po_number, idempotency_key=idempotency_key)


def _blocked(sctx, name: str, why: str):
    sctx.audit("tool.blocked", actor_type="ai", actor="Procurement Agent", input={"tool": name},
               result="blocked", reason=why, status="denied")
    sctx.db.commit()
    raise FlowException("PERMISSION_BOUNDARY", f"Tool '{name}' blocked: {why}", {"tool": name}, recoverable=False)


def call_tool(sctx, name: str, /, **args):
    tdef = TOOLS.get(name)
    if tdef is None:
        _blocked(sctx, name, "unknown tool")
    if name not in sctx.allowed_tools:
        _blocked(sctx, name, f"not allowed in step '{sctx.step.key}'")
    if tdef.scope not in sctx.definition.agent_scopes:
        _blocked(sctx, name, f"scope '{tdef.scope}' has not been granted to this agent")
    if tdef.destructive and not sctx.ctx.get("human_authorised_destructive"):
        _blocked(sctx, name, "destructive actions require explicit human authorisation")

    # One stable key per logical workflow step + tool + arguments. A retry after a process crash
    # therefore reuses the same key instead of creating a fresh external operation. Live adapters
    # must forward this key to providers that support idempotency.
    raw_key = json.dumps({"workflow": sctx.workflow.id, "step": sctx.step.id, "tool": name, "args": args},
                         sort_keys=True, separators=(",", ":"), default=str)
    idempotency_key = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()
    existing = (sctx.db.query(ToolExecution)
                .filter(ToolExecution.idempotency_key == idempotency_key)
                .first())
    if existing and existing.status == "completed":
        sctx.audit("tool.idempotency_replay", actor_type="tool", actor=tdef.integration.upper(),
                   input={"tool": name, "idempotency_key": idempotency_key},
                   output=existing.output, result="replayed", status="replayed")
        return existing.output

    started = time.perf_counter()
    execution = existing or ToolExecution(workflow_id=sctx.workflow.id, step_id=sctx.step.id, tool_name=name,
                                           idempotency_key=idempotency_key, status="started")
    if existing:
        execution.status = "started"
        execution.error = None
    else:
        sctx.db.add(execution)
    # Persist the in-flight marker before the external call. If the process dies afterwards, the
    # same idempotency key is reused on resume rather than silently generating a new operation.
    sctx.db.commit()
    try:
        adapter = get_adapter(sctx.db, tdef.integration, sctx.workflow.org_id)
        output = tdef.handler(sctx, adapter, idempotency_key=idempotency_key, **args)
        execution.status = "completed"
        execution.output = output
        execution.completed_at = datetime.now(timezone.utc)
        sctx.db.commit()
    except IntegrationError as exc:
        execution.status = "failed"
        execution.error = str(exc)
        sctx.db.commit()
        sctx.audit(f"tool.{name}", actor_type="tool", actor=tdef.integration.upper(), input={**args, "idempotency_key": idempotency_key}, result="error",
                   reason=str(exc), status="failed", duration_ms=int((time.perf_counter() - started) * 1000))
        from app.models import Integration
        row = sctx.db.query(Integration).filter(Integration.key == tdef.integration,
                                                Integration.org_id == sctx.workflow.org_id).first()
        if row is not None and "disconnected" not in str(exc):
            row.failures_total += 1
        raise FlowException(exc.code, str(exc), {"tool": name, "integration": tdef.integration}) from exc
    except Exception as exc:
        execution.status = "failed"
        execution.error = str(exc)
        sctx.db.commit()
        raise
    sctx.audit(f"tool.{name}", actor_type="tool", actor=tdef.integration.upper(),
               input={**args, "idempotency_key": idempotency_key}, output=output,
               result="ok", status="executed", duration_ms=int((time.perf_counter() - started) * 1000))
    return output
