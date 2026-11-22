"use client";
import Link from "next/link";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { Async, Badge, Button, Card, CardHeader, Dot, EmptyState, PageHeader, Stat, StatusBadge, cn } from "@/components/ui";
import { fmtDateTime, relTime, titleCase } from "@/lib/format";
import { humanAction } from "@/components/AuditTimeline";

const ACTOR = { ai: "blue", system: "slate", user: "orange", tool: "violet" };

function Throughput({ series }) {
  const max = Math.max(1, ...series.map((s) => s.completed));
  return (
    <div className="flex h-28 items-end gap-2 px-4 pb-3 pt-4" role="img" aria-label="Workflows completed per day, last 7 days">
      {series.map((s) => (
        <div key={s.date} className="flex flex-1 flex-col items-center gap-1">
          <span className="tnum text-[11px] text-slate-500">{s.completed}</span>
          <div className="w-full rounded-t bg-accent-500/85" style={{ height: `${Math.max(4, (s.completed / max) * 64)}px` }} />
          <span className="text-[10px] text-slate-400">{new Date(s.date + "T00:00:00").toLocaleDateString("en-IN", { weekday: "short" })}</span>
        </div>
      ))}
    </div>
  );
}

function Observability() {
  const state = useApi("/dashboard/observability", { interval: 15000 });
  return (
    <Card>
      <CardHeader title="Observability" subtitle="Workflow execution, agent actions, retries, interventions and API health" action={<Button size="sm" variant="ghost" onClick={state.reload}>Refresh</Button>} />
      <Async state={state} skeletonRows={3}>
        {(o) => (
          <div className="grid gap-px bg-slate-100 sm:grid-cols-2 lg:grid-cols-4 [&>div]:bg-white [&>div]:p-4">
            <div><div className="text-[11px] font-semibold uppercase text-slate-500">Workflow execution</div><dl className="mt-2 space-y-1 text-sm"><div className="flex justify-between"><dt className="text-slate-500">Completed</dt><dd className="tnum">{o.workflow_execution.completed}</dd></div><div className="flex justify-between"><dt className="text-slate-500">Failed</dt><dd className="tnum">{o.workflow_execution.failed}</dd></div><div className="flex justify-between"><dt className="text-slate-500">Avg engine time</dt><dd className="tnum">{o.workflow_execution.avg_duration_s ?? "—"}s</dd></div></dl></div>
            <div><div className="text-[11px] font-semibold uppercase text-slate-500">Agent & tool actions</div><dl className="mt-2 space-y-1 text-sm">{Object.entries(o.agent_actions).map(([k, v]) => <div key={k} className="flex justify-between"><dt className="text-slate-500">{titleCase(k)} events</dt><dd className="tnum">{v}</dd></div>)}<div className="flex justify-between"><dt className="text-slate-500">Tool failures</dt><dd className="tnum">{(o.tool_calls.error || 0) + (o.tool_calls.blocked || 0)}</dd></div></dl></div>
            <div><div className="text-[11px] font-semibold uppercase text-slate-500">Exceptions & humans</div><dl className="mt-2 space-y-1 text-sm"><div className="flex justify-between"><dt className="text-slate-500">Exceptions</dt><dd className="tnum">{o.exceptions.total}</dd></div><div className="flex justify-between"><dt className="text-slate-500">Auto-retries</dt><dd className="tnum">{o.exceptions.retries}</dd></div><div className="flex justify-between"><dt className="text-slate-500">Human decisions</dt><dd className="tnum">{o.human_interventions}</dd></div></dl></div>
            <div><div className="text-[11px] font-semibold uppercase text-slate-500">API (since start)</div><dl className="mt-2 space-y-1 text-sm"><div className="flex justify-between"><dt className="text-slate-500">Requests</dt><dd className="tnum">{o.api.requests}</dd></div><div className="flex justify-between"><dt className="text-slate-500">p50 / p95</dt><dd className="tnum">{o.api.p50_ms ?? "—"} / {o.api.p95_ms ?? "—"} ms</dd></div><div className="flex justify-between"><dt className="text-slate-500">4xx / 5xx</dt><dd className="tnum">{o.api.errors_4xx} / {o.api.errors_5xx}</dd></div></dl></div>
          </div>
        )}
      </Async>
    </Card>
  );
}

export default function Dashboard() {
  const { can } = useAuth();
  const state = useApi("/dashboard/summary", { interval: 4000 });
  const approvals = useApi(can("approvals:read") ? "/approvals?status=pending&page_size=4" : null, { interval: 6000 });
  const [obs, setObs] = useState(false);

  return (
    <>
      <PageHeader title="Operations dashboard" subtitle="Live view of every function FlowForge owns. Metrics are calculated from real workflow data."
        actions={<><Button size="sm" onClick={() => setObs(!obs)}>{obs ? "Hide" : "Show"} observability</Button>{can("requests:create") && <Button variant="primary" href="/functions/procurement">New procurement request</Button>}</>} />
      <Async state={state} skeletonRows={6}>
        {(d) => {
          const m = d.metrics;
          return (
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-6">
                <Stat label="Active workflows" value={m.active_workflows} hint="running or waiting" tone="blue" href="/workflows?status=active" />
                <Stat label="Completed today" value={m.completed_today} hint={`${m.completed_total} all-time`} tone="green" href="/workflows?status=completed" />
                <Stat label="Pending review" value={m.pending_review} hint="human decisions" tone={m.pending_review ? "amber" : "slate"} href={can("approvals:read") ? "/approvals" : undefined} />
                <Stat label="Open exceptions" value={m.open_exceptions} hint="need resolution" tone={m.open_exceptions ? "red" : "slate"} href={can("exceptions:read") ? "/exceptions" : undefined} />
                <Stat label="Automation rate" value={`${m.automation_rate}%`} hint="no human needed" tone="green" />
                <Stat label="Human intervention" value={`${m.human_intervention}%`} hint="judgment only" tone="amber" />
              </div>
              {obs && <Observability />}
              <div className="grid gap-4 lg:grid-cols-3">
                <Card className="lg:col-span-2">
                  <CardHeader title="Active workflows" subtitle="Click to open the live execution view" action={<Button size="sm" variant="ghost" href="/workflows">All workflows →</Button>} />
                  {d.active.length === 0 ? <EmptyState title="Nothing in flight" hint="Start a procurement request or run the demo to see FlowForge work." action={<Button variant="primary" size="sm" href="/functions/procurement">Start procurement</Button>} /> : (
                    <ul className="divide-y divide-slate-100">{d.active.map((w) => (
                      <li key={w.id}><Link href={`/workflows/${w.id}`} className="flex flex-wrap items-center gap-2 px-4 py-2.5 hover:bg-slate-50">
                        <span className="font-mono text-xs text-slate-400">WF-{1000 + w.id}</span><span className="min-w-0 flex-1 truncate text-sm font-medium">{w.title}</span>
                        <span className="hidden text-xs text-slate-500 sm:inline">{titleCase(w.current_step)}</span><StatusBadge status={w.status} /><span className="w-14 shrink-0 text-right text-xs text-slate-400">{relTime(w.created_at)}</span></Link></li>
                    ))}</ul>
                  )}
                </Card>
                <Card>
                  <CardHeader title="Completed per day" subtitle="Last 7 days" />
                  <Throughput series={d.throughput} />
                  <div className="border-t border-slate-100 px-4 py-3">
                    <div className="mb-2 text-[11px] font-semibold uppercase tracking-wide text-slate-500">Connected systems</div>
                    <div className="grid grid-cols-2 gap-x-3 gap-y-1.5">{d.integrations.map((i) => <Link key={i.key} href="/integrations" className="flex items-center gap-1.5 text-xs text-slate-700 hover:text-slate-900"><Dot tone={i.status === "connected" ? "green" : i.status === "degraded" ? "amber" : "red"} />{i.name}</Link>)}</div>
                  </div>
                </Card>
              </div>
              <div className="grid gap-4 lg:grid-cols-3">
                {can("approvals:read") && (
                  <Card>
                    <CardHeader title="Pending approvals" subtitle="Where FlowForge is waiting for judgment" action={<Button size="sm" variant="ghost" href="/approvals">Open center →</Button>} />
                    <Async state={approvals} skeletonRows={2} empty={Object.assign((x) => !x.items.length, { element: <EmptyState title="All clear" hint="No decisions waiting on a human." /> })}>
                      {(a) => <ul className="divide-y divide-slate-100">{a.items.map((x) => <li key={x.id}><Link href="/approvals" className="block px-4 py-2.5 hover:bg-slate-50"><div className="flex items-center gap-1.5"><Badge tone={x.level === 3 ? "orange" : "amber"}>L{x.level}</Badge><Badge>{x.assigned_role}</Badge><span className="text-[11px] text-slate-400">{relTime(x.created_at)}</span></div><div className="mt-1 line-clamp-2 text-sm text-slate-800">{x.title}</div></Link></li>)}</ul>}
                    </Async>
                  </Card>
                )}
                <Card className={can("approvals:read") ? "lg:col-span-2" : "lg:col-span-3"}>
                  <CardHeader title="Recent activity" subtitle="Audited actions by FlowForge, tools and people" action={can("audit:read") && <Button size="sm" variant="ghost" href="/audit">Audit trail →</Button>} />
                  <ul className="divide-y divide-slate-100">
                    {d.recent_activity.map((e) => (
                      <li key={e.id} className="flex items-start gap-3 px-4 py-2"><span className="tnum w-20 shrink-0 pt-0.5 text-xs text-slate-400">{fmtDateTime(e.ts)}</span><Badge tone={ACTOR[e.actor_type]} className="mt-0.5">{e.actor_type === "ai" ? "AI" : titleCase(e.actor_type)}</Badge>
                        <div className="min-w-0 flex-1 text-sm"><span className="font-medium">{humanAction(e.action)}</span>{e.workflow && e.workflow_id && <Link href={`/workflows/${e.workflow_id}`} className="ml-2 text-xs text-accent-600 hover:underline">{e.workflow}</Link>}<div className="truncate text-xs text-slate-500">{e.actor}{e.reason ? ` — ${e.reason}` : ""}</div></div></li>
                    ))}
                  </ul>
                </Card>
              </div>
            </div>
          );
        }}
      </Async>
    </>
  );
}
