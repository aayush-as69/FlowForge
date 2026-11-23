"use client";
import { useMemo, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { Async, Badge, Button, Card, CardHeader, EmptyState, ErrorState, Json, Kv, PageHeader, StatusBadge, Tabs, cn } from "@/components/ui";
import WorkflowGraph from "@/components/WorkflowGraph";
import ApprovalPanel from "@/components/ApprovalPanel";
import AuditTimeline, { humanAction } from "@/components/AuditTimeline";
import { StepOutput } from "@/components/StepViews";
import Explanation from "@/components/Explanation";
import ExceptionBlock from "@/components/ExceptionBlock";
import { duration, fmtDate, fmtDateTime, fmtTime, inr, relTime, titleCase } from "@/lib/format";

const ACTIVE = ["pending", "running", "waiting_human"];

function Inspector({ step, wf, reload }) {
  const excs = wf.exceptions.filter((e) => e.step_id === step.id);
  const approvals = wf.approvals.filter((a) => a.step_id === step.id);
  return (
    <Card className="ff-enter" key={step.id}>
      <CardHeader title={step.name} subtitle={step.action} action={<StatusBadge status={step.status} />} />
      <div className="space-y-4 p-4">
        <dl className="grid gap-x-6 sm:grid-cols-2">
          <Kv label="Status"><StatusBadge status={step.status} /></Kv>
          <Kv label="Timestamp">{step.started_at ? `${fmtTime(step.started_at)} → ${step.completed_at ? fmtTime(step.completed_at) : "…"}` : "Not started"}{step.duration_ms !== null && <span className="ml-1 text-xs text-slate-500">({duration(step.duration_ms)}{step.attempts > 1 ? `, ${step.attempts} attempts` : ""})</span>}</Kv>
          <Kv label="Decision">{step.decision}</Kv>
          <Kv label="Reason"><span className="text-[13px]">{step.reason}</span></Kv>
        </dl>
        {step.error && <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800"><b>Error / exception:</b> {step.error}</div>}
        {step.input && <div><div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Input</div><Json value={step.input} className="max-h-32" /></div>}
        <div><div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Output</div><StepOutput step={step} /></div>
        {excs.length > 0 && (
          <div>
            <div className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Exceptions on this step</div>
            <div className="space-y-2">{excs.map((e) => <ExceptionBlock key={e.id} e={e} />)}</div>
          </div>
        )}
        {approvals.filter((a) => a.status === "pending").map((a) => <ApprovalPanel key={a.id} approval={a} onDone={reload} />)}
      </div>
    </Card>
  );
}

function Overview({ wf }) {
  const r = wf.request;
  return (
    <div className="grid gap-4 lg:grid-cols-2">
      <div className="space-y-4">
        <div><h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Request · original input</h3>
          <pre className="whitespace-pre-wrap rounded-md bg-slate-50 p-3 font-sans text-sm text-slate-800 ring-1 ring-inset ring-slate-200">{r?.raw_text}</pre>
          <div className="mt-1 text-xs text-slate-500">via {titleCase(r?.source)} · submitted by {r?.requester}</div></div>
        <div><h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Extracted data · what FlowForge understood</h3>
          <dl className="rounded-md ring-1 ring-inset ring-slate-200 px-3 divide-y divide-slate-100">
            <Kv label="Request type">{titleCase(r?.category)}</Kv><Kv label="Item">{r?.item}</Kv><Kv label="Quantity">{r?.quantity}</Kv>
            <Kv label="Purpose">{r?.purpose}</Kv><Kv label="Required date">{r?.required_date ? `${fmtDate(r.required_date)}${r.required_date_text ? ` (“${r.required_date_text}”)` : ""}` : null}</Kv>
            <Kv label="Budget">{inr(r?.budget)}</Kv><Kv label="Requirements">{r?.requirements}</Kv>
            <Kv label="Confidence">{Math.round((r?.confidence || 0) * 100)}% · {r?.extraction_engine}{r?.corrected && <Badge tone="violet" className="ml-1.5">human-corrected</Badge>}</Kv>
          </dl></div>
      </div>
      <div><h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-slate-500">Plan · what FlowForge intended to do</h3>
        <ol className="space-y-1.5">{wf.plan.map((p, i) => {
          const s = wf.steps.find((x) => x.key === p.step);
          return <li key={p.step} className="flex gap-2 text-sm"><span className="tnum w-5 text-right text-xs text-slate-400">{i + 1}</span><span className={cn("flex-1", s?.status === "pending" ? "text-slate-500" : "text-slate-800")}>{p.intent}</span>{s && <StatusBadge status={s.status} />}</li>;
        })}</ol></div>
    </div>
  );
}

function Decisions({ wf }) {
  if (!wf.decisions.length) return <EmptyState title="No decisions yet" hint="Decisions appear as the workflow evaluates vendors and applies decision rules." />;
  return (
    <ul className="divide-y divide-slate-100">
      {wf.decisions.map((d) => (
        <li key={d.id} className="py-3">
          <div className="flex flex-wrap items-center gap-1.5"><span className="text-sm font-semibold">{titleCase(d.kind)}</span><Badge tone={d.actor_type === "user" ? "orange" : d.actor_type === "ai" ? "blue" : "slate"}>{d.actor}</Badge>{d.level && <Badge tone={{ 1: "green", 2: "amber", 3: "orange" }[d.level]}>Level {d.level}</Badge>}<Badge tone="slate">{d.outcome}</Badge><span className="text-[11px] text-slate-500">{fmtTime(d.created_at)}</span></div>
          <p className="mt-1 text-sm text-slate-700">{d.reason}</p>
          {d.kind === "autonomy" && <details className="mt-1"><summary className="cursor-pointer text-xs text-slate-500">Rule trace</summary><ul className="mt-1 space-y-0.5">{d.rule_trace.map((t, i) => <li key={i} className="text-xs text-slate-600"><span className={t.matched ? "text-amber-600" : "text-emerald-600"}>{t.matched ? "▲" : "✓"}</span> <span className="font-mono text-[11px]">{t.rule}</span> — {t.detail}</li>)}</ul></details>}
        </li>
      ))}
    </ul>
  );
}

// Poll quickly while the workflow is moving, slowly while it waits for a person, and not at all once it has finished.
const workflowPollMs = (wf) => (!wf ? 1500 : ["completed", "failed", "cancelled"].includes(wf.status) ? 0 : wf.status === "waiting_human" ? 6000 : 1500);

export default function WorkflowPage() {
  const { id } = useParams();
  const { can } = useAuth();
  const state = useApi(`/workflows/${id}`, { interval: workflowPollMs });
  const wf = state.data;
  const [picked, setPicked] = useState(null);
  const [tab, setTab] = useState("overview");
  const [acting, setActing] = useState(null);
  const [actionError, setActionError] = useState(null);

  const autoStep = useMemo(() => {
    if (!wf) return null;
    return wf.steps.find((s) => ["waiting_human", "running", "failed"].includes(s.status)) || [...wf.steps].reverse().find((s) => s.status !== "pending") || wf.steps[0];
  }, [wf]);
  const selected = wf ? wf.steps.find((s) => s.id === picked) || autoStep : null;

  async function act(kind) {
    setActing(kind); setActionError(null);
    try { await api(`/workflows/${id}/${kind}`, { method: "POST" }); await state.reload(); } catch (e) { setActionError(e.message); } finally { setActing(null); }
  }

  if (!wf) return <Card><Async state={state} skeletonRows={8}>{() => null}</Async></Card>;
  const pendingApprovals = wf.approvals.filter((a) => a.status === "pending");
  const exceptions = wf.exceptions;
  const actions = wf.audit.filter((e) => e.action.startsWith("tool."));
  const tabs = [
    { key: "overview", label: "Request & plan" },
    { key: "why", label: "Why this happened" },
    { key: "actions", label: "Actions", count: actions.length },
    { key: "decisions", label: "Decisions", count: wf.decisions.length },
    { key: "exceptions", label: "Exceptions", count: exceptions.length },
    { key: "human", label: "Human intervention", count: wf.approvals.length },
    { key: "audit", label: "Audit timeline", count: wf.audit.length },
  ];

  return (
    <>
      <div className="mb-3 text-xs text-slate-500"><Link href="/workflows" className="hover:text-slate-800">Workflows</Link> / {wf.ref}</div>
      <PageHeader
        title={wf.title}
        eyebrow={`${wf.ref} · ${titleCase(wf.function_key)}${wf.is_demo ? " · Demo" : ""}`}
        subtitle={`Requested by ${wf.requester || "—"} · started ${relTime(wf.started_at || wf.created_at)}`}
        actions={<>
          <StatusBadge status={wf.status} />
          {wf.status === "failed" && can("workflows:operate") && <Button variant="primary" size="sm" loading={acting === "retry"} onClick={() => act("retry")}>Retry from failed step</Button>}
          {ACTIVE.includes(wf.status) && can("workflows:operate") && <Button size="sm" variant="danger" loading={acting === "cancel"} onClick={() => { if (confirm("Cancel this workflow? Pending steps will be skipped.")) act("cancel"); }}>Cancel</Button>}
        </>}
      />
      {actionError && <div role="alert" className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{actionError}</div>}
      {state.error && <div className="mb-3 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900">Live updates interrupted: {state.error.message} <button className="underline" onClick={state.reload}>Retry</button></div>}
      {wf.status === "failed" && <div role="alert" className="mb-4 rounded-md border border-red-200 bg-red-50 p-3 text-sm text-red-800"><b>Workflow failed.</b> {wf.error} <span className="text-red-700/80">Its state is saved — an operator can retry from the failed step{can("workflows:operate") ? "." : " (manager or admin)."}</span></div>}
      {wf.status === "cancelled" && <div className="mb-4 rounded-md border border-slate-200 bg-slate-100 p-3 text-sm text-slate-700"><b>Workflow cancelled.</b> {wf.error}</div>}
      {wf.status === "completed" && (
        <Card className="mb-4 border-emerald-200 bg-emerald-50/50 ff-enter">
          <div className="flex flex-wrap items-start gap-4 p-4">
            <div className="grid size-9 place-items-center rounded-full bg-emerald-500 text-white">✓</div>
            <div className="min-w-0 flex-1"><div className="text-sm font-semibold text-emerald-900">Procurement complete</div><p className="mt-0.5 text-sm text-emerald-900/90">{wf.outcome}</p></div>
            {wf.purchase_order && <div className="text-right text-xs text-slate-600"><div className="font-mono text-sm font-semibold text-slate-900">{wf.purchase_order.po_number}</div><div>{wf.purchase_order.vendor} · {inr(wf.purchase_order.total)}</div><div>ERP {wf.purchase_order.erp_ref}</div></div>}
          </div>
        </Card>
      )}
      {pendingApprovals.length > 0 && wf.status === "waiting_human" && (
        <div className="mb-4 space-y-3"><div className="flex items-center gap-2 text-sm font-semibold text-forge-600"><span className="inline-block size-2 rounded-full bg-forge-500 ff-waiting" /> FlowForge is paused — a human decision is needed</div>
          {pendingApprovals.map((a) => <ApprovalPanel key={a.id} approval={a} onDone={state.reload} />)}</div>
      )}

      <div className="grid gap-4 lg:grid-cols-[minmax(0,420px)_1fr]">
        <Card>
          <CardHeader title="Workflow" subtitle={`${wf.progress.done}/${wf.progress.total} steps done · click a node to inspect`} />
          <div className="p-4"><WorkflowGraph steps={wf.steps} exceptions={exceptions} approvals={wf.approvals} selectedId={selected?.id} onSelect={setPicked} /></div>
        </Card>
        <div className="min-w-0 space-y-4">
          {selected && <Inspector step={selected} wf={wf} reload={state.reload} />}
          <Card>
            <Tabs tabs={tabs} value={tab} onChange={setTab} />
            <div className="p-4">
              {tab === "overview" && <Overview wf={wf} />}
              {tab === "why" && <Explanation workflowId={wf.id} />}
              {tab === "actions" && (actions.length ? (
                <ul className="divide-y divide-slate-100">{actions.map((e) => <li key={e.id} className="flex flex-wrap items-center gap-2 py-2 text-sm"><span className="tnum w-20 font-mono text-xs text-slate-500">{fmtTime(e.ts)}</span><Badge tone="violet">{e.actor}</Badge><span className="font-medium">{humanAction(e.action.replace("tool.", ""))}</span><Badge tone={e.result === "ok" ? "green" : "red"}>{e.result}</Badge>{e.duration_ms !== null && <span className="tnum text-[11px] text-slate-400">{e.duration_ms} ms</span>}{e.reason && <span className="w-full pl-[88px] text-xs text-red-600">{e.reason}</span>}</li>)}</ul>
              ) : <EmptyState title="No actions executed yet" hint="Tool calls to ERP, vendor database, email and other systems appear here." />)}
              {tab === "decisions" && <Decisions wf={wf} />}
              {tab === "exceptions" && (exceptions.length ? <div className="space-y-2">{exceptions.map((e) => <ExceptionBlock key={e.id} e={e} />)}</div> : <EmptyState title="No exceptions" hint="This workflow has run without anything going wrong." />)}
              {tab === "human" && (wf.approvals.length ? <div className="space-y-3">{wf.approvals.map((a) => <ApprovalPanel key={a.id} approval={a} defaultOpen={a.status === "pending"} onDone={state.reload} />)}</div> : <EmptyState title="No human involvement" hint="FlowForge handled every step autonomously." />)}
              {tab === "audit" && <div className="-m-4"><AuditTimeline events={wf.audit} /></div>}
            </div>
          </Card>
        </div>
      </div>
    </>
  );
}
