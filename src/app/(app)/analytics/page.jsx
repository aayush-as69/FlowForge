"use client";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { barHeights, hoursLabel, money } from "@/lib/analytics";
import { Async, Card, CardHeader, PageHeader, Stat, Tabs } from "@/components/ui";

function RateBar({ label, value, tone = "bg-forge-500" }) {
  return (
    <div>
      <div className="flex justify-between text-sm"><span className="text-slate-600">{label}</span><span className="tnum font-medium">{value}%</span></div>
      <div className="mt-1 h-2 rounded bg-slate-100" role="img" aria-label={`${label}: ${value}%`}><div className={`h-2 rounded ${tone}`} style={{ width: `${Math.min(value, 100)}%` }} /></div>
    </div>
  );
}

export default function Analytics() {
  const [days, setDays] = useState("30");
  const state = useApi(`/analytics/overview?days=${days}`, { interval: 30000 });
  return (
    <>
      <PageHeader title="Analytics" subtitle="How much work FlowForge handled, where people are the bottleneck, what goes wrong most, and an estimate of the effort saved." />
      <Tabs value={days} onChange={setDays} tabs={[{ key: "7", label: "7 days" }, { key: "30", label: "30 days" }, { key: "90", label: "90 days" }]} />
      <div className="mt-4 space-y-4">
        <Async state={state} skeletonRows={6}>
          {(d) => {
            const heights = barHeights(d.daily.map((x) => x.completed));
            const r = d.roi;
            return (
              <>
                <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
                  <Stat label="Workflows started" value={d.volume.started} hint={`${d.volume.completed} completed · ${d.volume.failed} failed`} />
                  <Stat label="Automation rate" value={`${d.rates.automation_pct}%`} hint="Completed with no human decision" tone="green" />
                  <Stat label="Exception rate" value={`${d.rates.exception_pct}%`} hint="Workflows that hit an exception" tone={d.rates.exception_pct > 20 ? "amber" : "slate"} />
                  <Stat label="Avg approval wait" value={hoursLabel(d.approval_latency.avg_hours)} hint={d.approval_latency.slowest_role ? `Slowest: ${d.approval_latency.slowest_role.role}` : "No decisions yet"} />
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <Card>
                    <CardHeader title="Rates" />
                    <div className="space-y-3 p-4">
                      <RateBar label="Success (completed vs failed)" value={d.rates.success_pct} tone="bg-emerald-500" />
                      <RateBar label="Automation" value={d.rates.automation_pct} />
                      <RateBar label="Human intervention" value={d.rates.human_intervention_pct} tone="bg-amber-500" />
                      <RateBar label="Exceptions" value={d.rates.exception_pct} tone="bg-red-400" />
                    </div>
                  </Card>
                  <Card>
                    <CardHeader title="Completed per day" subtitle="Last 30 days at most" />
                    <div className="flex h-36 items-end gap-0.5 p-4" role="img" aria-label="Completed workflows per day">
                      {d.daily.map((x, i) => <div key={x.date} title={`${x.date}: ${x.completed}`} className="flex-1 rounded-t bg-forge-500/80" style={{ height: `${heights[i]}%` }} />)}
                    </div>
                  </Card>
                </div>
                <div className="grid gap-4 lg:grid-cols-2">
                  <Card>
                    <CardHeader title="Approval bottleneck" subtitle="Average time from request to decision, by role" />
                    <ul className="divide-y divide-slate-100">
                      {d.approval_latency.by_role.length === 0 && <li className="p-4 text-sm text-slate-500">No decided approvals in this period.</li>}
                      {d.approval_latency.by_role.map((x) => (
                        <li key={x.role} className="flex justify-between px-4 py-2.5 text-sm"><span className="capitalize text-slate-700">{x.role} <span className="text-slate-400">({x.count})</span></span><span className="tnum font-medium">{hoursLabel(x.avg_hours)}</span></li>
                      ))}
                    </ul>
                  </Card>
                  <Card>
                    <CardHeader title="Most common failure reasons" subtitle="Exceptions raised, and how many were recovered" />
                    <ul className="divide-y divide-slate-100">
                      {d.failure_reasons.length === 0 && <li className="p-4 text-sm text-slate-500">No exceptions in this period.</li>}
                      {d.failure_reasons.map((x) => (
                        <li key={x.code} className="flex justify-between px-4 py-2.5 text-sm"><span className="font-mono text-xs text-slate-700">{x.code}</span><span className="tnum text-slate-600">{x.count} · {x.recovered} recovered</span></li>
                      ))}
                    </ul>
                  </Card>
                </div>
                <Card>
                  <CardHeader title="Estimated savings" subtitle="An estimate from the assumptions below, not billing data" />
                  <div className="grid gap-px bg-slate-100 sm:grid-cols-2 lg:grid-cols-4 [&>div]:bg-white [&>div]:p-4">
                    <div><div className="text-[11px] font-semibold uppercase text-slate-500">Manual cost avoided</div><div className="tnum mt-1 text-xl font-semibold">{money(r.manual_cost, r.currency)}</div></div>
                    <div><div className="text-[11px] font-semibold uppercase text-slate-500">FlowForge cost</div><div className="tnum mt-1 text-xl font-semibold">{money(r.total_cost, r.currency)}</div><div className="mt-1 text-xs text-slate-500">AI {money(r.ai_cost, r.currency)} · API {money(r.api_cost, r.currency)} · Human {money(r.human_cost, r.currency)}</div></div>
                    <div><div className="text-[11px] font-semibold uppercase text-slate-500">Estimated savings</div><div className="tnum mt-1 text-xl font-semibold text-emerald-700">{money(r.savings, r.currency)}</div></div>
                    <div><div className="text-[11px] font-semibold uppercase text-slate-500">Hours saved</div><div className="tnum mt-1 text-xl font-semibold">{r.hours_saved}</div></div>
                  </div>
                  <details className="border-t border-slate-100 p-4 text-xs text-slate-600">
                    <summary className="cursor-pointer font-medium">Assumptions used</summary>
                    <p className="mt-2">{r.assumptions.manual_minutes_per_request} min of manual work per request at {money(r.assumptions.hourly_cost, r.currency)}/h; {r.assumptions.human_review_minutes} min per human review; {money(r.assumptions.llm_call_cost, r.currency)} per model call; {money(r.assumptions.tool_call_cost, r.currency)} per tool call. Change them with the ROI_* environment variables.</p>
                  </details>
                </Card>
              </>
            );
          }}
        </Async>
      </div>
    </>
  );
}
