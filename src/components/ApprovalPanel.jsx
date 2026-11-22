"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { Badge, Button, StatusBadge, cn, inputCls } from "@/components/ui";
import { PolicyList, VendorTable } from "@/components/StepViews";
import { fmtDateTime, inr, relTime } from "@/lib/format";

const RISK = { low: "green", medium: "amber", high: "red" };
const LEVEL = { 2: ["amber", "Level 2 · Review"], 3: ["orange", "Level 3 · Human decision"] };

function Block({ title, children, tone }) {
  return (
    <div className={cn("rounded-md p-3", tone === "rec" ? "bg-accent-50 ring-1 ring-inset ring-accent-100" : "bg-slate-50")}>
      <div className={cn("mb-1 text-[11px] font-semibold uppercase tracking-wide", tone === "rec" ? "text-accent-700" : "text-slate-500")}>{title}</div>
      <div className="text-sm leading-relaxed text-slate-800">{children}</div>
    </div>
  );
}

export default function ApprovalPanel({ approval: a, onDone, defaultOpen = true }) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const [modifying, setModifying] = useState(false);
  const [vendorId, setVendorId] = useState("");
  const [open, setOpen] = useState(defaultOpen);
  const sd = a.supporting_data || {};
  const pending = a.status === "pending";
  const [tone, levelLabel] = LEVEL[a.level] || LEVEL[2];
  const vendorOptions = sd.vendor_options || [];

  async function act(action, modification) {
    setBusy(action);
    setError(null);
    try {
      await api(`/approvals/${a.id}/decision`, { method: "POST", body: { action, note: note || null, modification: modification || null } });
      onDone?.(action);
    } catch (e) {
      setError(e.message);
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="rounded-lg border border-slate-200 bg-white">
      <button className="flex w-full items-start justify-between gap-3 px-4 py-3 text-left" onClick={() => setOpen(!open)} aria-expanded={open}>
        <div className="min-w-0">
          <div className="mb-1 flex flex-wrap items-center gap-1.5">
            <Badge tone={tone}>{levelLabel}</Badge>
            <Badge tone={a.kind === "exception_review" ? "red" : "blue"}>{a.kind === "exception_review" ? "Exception review" : "Approval"}</Badge>
            <Badge>{a.workflow_ref}</Badge>
            {a.escalated && <Badge tone="orange">Escalated</Badge>}
            {!pending && <StatusBadge status={a.status} />}
          </div>
          <div className="text-sm font-semibold text-slate-900">{a.title}</div>
          <div className="mt-0.5 text-xs text-slate-500">Requested by {a.requester || "—"} · assigned to <span className="font-medium">{a.assigned_role}</span> · {relTime(a.created_at)}</div>
        </div>
        <span className="mt-1 text-slate-400">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="space-y-3 border-t border-slate-100 p-4">
          <div className="grid gap-3 md:grid-cols-2">
            <Block title="What happened">{a.summary}</Block>
            <Block title="Why a human is needed">{a.reason}</Block>
            <Block title="FlowForge recommendation" tone="rec">{a.recommendation}</Block>
            <Block title="Risk"><Badge tone={RISK[a.risk_level]} className="mr-1.5">{a.risk_level}</Badge>{a.risk}</Block>
          </div>
          {sd.ai_rationale && <div className="rounded-md border border-dashed border-slate-300 p-3 text-xs text-slate-600"><span className="font-semibold">AI rationale:</span> {sd.ai_rationale}</div>}
          {sd.price && (
            <div className="flex flex-wrap gap-6 rounded-md ring-1 ring-inset ring-slate-200 px-3 py-2 text-sm">
              <div><div className="text-[11px] uppercase text-slate-500">Quoted unit price</div><div className="tnum font-semibold">{inr(sd.price.unit)}</div></div>
              <div><div className="text-[11px] uppercase text-slate-500">Historical average</div><div className="tnum font-semibold">{inr(sd.price.historical)}</div></div>
              <div><div className="text-[11px] uppercase text-slate-500">Deviation</div><div className="tnum font-semibold text-amber-700">+{sd.price.delta_pct}%</div></div>
              <div><div className="text-[11px] uppercase text-slate-500">Budget</div><div className="tnum font-semibold">{inr(sd.budget)}</div></div>
            </div>
          )}
          {sd.alternatives_rejected?.length > 0 && (
            <div>
              <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Alternatives FlowForge checked</div>
              <ul className="space-y-1">{sd.alternatives_rejected.map((r) => <li key={r.vendor} className="text-xs text-slate-700"><span className="mr-1 text-red-500">✕</span><span className="font-medium">{r.vendor}</span> — {r.why.join("; ")}</li>)}</ul>
            </div>
          )}
          {sd.offers && <VendorTable offers={sd.offers} selectedId={sd.selected?.vendor_id} compact />}
          {sd.policy?.results && <details className="text-sm"><summary className="cursor-pointer text-xs font-medium text-slate-600">Policy results</summary><div className="mt-2"><PolicyList results={sd.policy.results} /></div></details>}
          {Array.isArray(sd.policy) && <PolicyList results={sd.policy} />}

          {!pending ? (
            <div className="rounded-md bg-slate-50 p-3 text-sm"><span className="font-medium">{a.decided_by}</span> ({a.decided_by_role}) <StatusBadge status={a.status} /> · {fmtDateTime(a.decided_at)}{a.decision_note && <p className="mt-1 text-slate-600">“{a.decision_note}”</p>}</div>
          ) : (
            <div className="space-y-2 border-t border-slate-100 pt-3">
              {a.can_decide === false && <div className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">{a.cannot_decide_reason}</div>}
              <textarea className={cn(inputCls, "h-16 py-2")} placeholder={a.level === 3 ? "Written justification (required for Level 3 decisions)" : "Note (optional) — recorded in the audit trail"} value={note} onChange={(e) => setNote(e.target.value)} />
              {modifying && (
                <div className="flex flex-wrap items-center gap-2 rounded-md bg-slate-50 p-2">
                  <select className={cn(inputCls, "w-64")} value={vendorId} onChange={(e) => setVendorId(e.target.value)} aria-label="Choose vendor">
                    <option value="">Choose a different vendor…</option>
                    {vendorOptions.map((o) => <option key={o.vendor_id} value={o.vendor_id}>{o.name} — {inr(o.total)} · {o.delivery_days}d</option>)}
                  </select>
                  <Button variant="primary" size="sm" disabled={!vendorId} loading={busy === "modify"} onClick={() => act("modify", { vendor_id: Number(vendorId) })}>Apply modification</Button>
                  <Button size="sm" variant="ghost" onClick={() => setModifying(false)}>Cancel</Button>
                </div>
              )}
              {error && <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}
              <div className="flex flex-wrap gap-2">
                {a.options.includes("approve") && <Button variant="success" disabled={a.can_decide === false} loading={busy === "approve"} onClick={() => act("approve")}>Approve</Button>}
                {a.options.includes("reject") && <Button variant="danger" disabled={a.can_decide === false} loading={busy === "reject"} onClick={() => act("reject")}>Reject</Button>}
                {a.options.includes("modify") && <Button disabled={a.can_decide === false || !vendorOptions.length} onClick={() => setModifying(true)}>Modify</Button>}
                {a.options.includes("escalate") && <Button variant="ghost" disabled={a.can_decide === false} loading={busy === "escalate"} onClick={() => act("escalate")}>Escalate</Button>}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
