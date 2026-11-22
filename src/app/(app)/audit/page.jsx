"use client";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { Async, Button, Card, EmptyState, PageHeader, Pager, cn, inputCls } from "@/components/ui";
import { AuditRow } from "@/components/AuditTimeline";

const ACTORS = [["", "All actors"], ["ai", "AI agents"], ["system", "System"], ["user", "Humans"], ["tool", "Tools"]];

export default function Audit() {
  const [actor, setActor] = useState("");
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [steps, setSteps] = useState(false);
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page, page_size: 30, include_steps: steps });
  if (actor) params.set("actor_type", actor);
  if (query) params.set("q", query);
  const state = useApi(`/audit?${params}`, { interval: 8000 });
  return (
    <>
      <PageHeader title="Audit trail" subtitle="What FlowForge did, why, what it couldn’t do, when it asked a human and what the human decided. Click an event for its input and output." />
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 p-3">
          <div className="flex flex-wrap gap-1">{ACTORS.map(([k, l]) => <button key={k} onClick={() => { setActor(k); setPage(1); }} className={cn("rounded px-2.5 py-1 text-xs font-medium", actor === k ? "bg-ink-900 text-white" : "text-slate-600 hover:bg-slate-100")}>{l}</button>)}
            <label className="ml-2 flex items-center gap-1.5 text-xs text-slate-600"><input type="checkbox" checked={steps} onChange={(e) => { setSteps(e.target.checked); setPage(1); }} />Include step events</label></div>
          <form onSubmit={(e) => { e.preventDefault(); setQuery(q); setPage(1); }} className="flex gap-2"><input className={cn(inputCls, "h-8 w-56")} placeholder="Search action, actor, reason" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search audit events" /><Button size="sm" type="submit">Search</Button></form>
        </div>
        <Async state={state} skeletonRows={8} empty={Object.assign((d) => !d.items.length, { element: <EmptyState title="No audit events match" hint="Clear the search or actor filter." /> })}>
          {(d) => (<><ul className="divide-y divide-slate-100">{d.items.map((e) => <AuditRow key={e.id} e={e} showWorkflow showDate />)}</ul><Pager page={d.page} pages={d.pages} total={d.total} onPage={setPage} /></>)}
        </Async>
      </Card>
    </>
  );
}
