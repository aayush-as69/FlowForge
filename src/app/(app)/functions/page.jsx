"use client";
import Link from "next/link";
import { useApi } from "@/lib/hooks";
import { Async, Badge, Button, Card, Dot, PageHeader, cn } from "@/components/ui";

const REUSED = ["Workflow engine", "Decision engine", "Exception engine", "Approval system", "Policy engine", "Audit system", "Integration layer", "AI orchestration"];

export default function Functions() {
  const state = useApi("/functions");
  return (
    <>
      <PageHeader title="Business functions" subtitle="FlowForge takes ownership of an entire function — from first input to finished outcome. Procurement is live; the rest reuse the same engines." />
      <Async state={state} skeletonRows={5}>
        {(fns) => (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {fns.map((f) => {
              const active = f.status === "active";
              const body = (
                <Card className={cn("h-full p-5 transition-shadow", active ? "border-accent-500/50 hover:shadow-md" : "opacity-80")}>
                  <div className="flex items-center justify-between"><div className="flex items-center gap-2"><Dot tone={active ? "green" : "slate"} /><span className={cn("text-xs font-medium", active ? "text-emerald-700" : "text-slate-500")}>{active ? "Active" : "Coming soon"}</span></div>{active && <Badge tone="blue">Fully interactive</Badge>}</div>
                  <h2 className="mt-3 text-lg font-semibold tracking-tight">{f.name}</h2>
                  <p className="mt-1 text-sm text-slate-600">{f.description}</p>
                  <div className="mt-3 rounded bg-slate-50 px-2.5 py-1.5 font-mono text-[11px] text-slate-500">{f.outcome}</div>
                  {active && f.stats && <div className="mt-4 flex gap-6 text-sm"><div><div className="tnum text-xl font-semibold">{f.stats.active}</div><div className="text-[11px] text-slate-500">active</div></div><div><div className="tnum text-xl font-semibold">{f.stats.completed}</div><div className="text-[11px] text-slate-500">completed</div></div><div><div className="tnum text-xl font-semibold">{f.stats.total}</div><div className="text-[11px] text-slate-500">total</div></div></div>}
                  {active ? <div className="mt-4"><Button variant="primary" size="sm">Open procurement →</Button></div> : <div className="mt-4 text-xs text-slate-400">Planned on the same engine — no platform rebuild required.</div>}
                </Card>
              );
              return active ? <Link key={f.key} href={`/functions/${f.key}`}>{body}</Link> : <div key={f.key} aria-disabled>{body}</div>;
            })}
          </div>
        )}
      </Async>
      <Card className="mt-6 p-5">
        <h2 className="text-sm font-semibold">One platform, many functions</h2>
        <p className="mt-1 text-sm text-slate-600">Procurement is an implementation of a reusable function-automation engine. A new function only declares its steps, policies and exception types; everything below is shared.</p>
        <div className="mt-3 flex flex-wrap gap-1.5">{REUSED.map((r) => <Badge key={r} tone="blue">{r}</Badge>)}</div>
      </Card>
    </>
  );
}
