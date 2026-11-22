"use client";
import { Suspense, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useApi } from "@/lib/hooks";
import { Async, Badge, Button, Card, EmptyState, PageHeader, Pager, StatusBadge, cn, inputCls } from "@/components/ui";
import { inr, relTime, titleCase } from "@/lib/format";

const FILTERS = [["", "All"], ["active", "Active"], ["waiting_human", "Waiting for human"], ["completed", "Completed"], ["failed", "Failed"], ["cancelled", "Cancelled"]];

function List() {
  const initial = useSearchParams().get("status") || "";
  const [status, setStatus] = useState(initial);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({ page, page_size: 15 });
  if (status) params.set("status", status);
  if (query) params.set("q", query);
  const state = useApi(`/workflows?${params}`, { interval: 5000 });
  return (
    <>
      <PageHeader title="Workflows" subtitle="Every function execution, with its full state, decisions and audit trail." actions={<Button variant="primary" href="/functions/procurement">New request</Button>} />
      <Card>
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-100 p-3">
          <div className="flex flex-wrap gap-1">{FILTERS.map(([k, l]) => <button key={k} onClick={() => { setStatus(k); setPage(1); }} className={cn("rounded px-2.5 py-1 text-xs font-medium", status === k ? "bg-ink-900 text-white" : "text-slate-600 hover:bg-slate-100")}>{l}</button>)}</div>
          <form onSubmit={(e) => { e.preventDefault(); setQuery(q); setPage(1); }} className="flex gap-2"><input className={cn(inputCls, "h-8 w-56")} placeholder="Search title or WF-1042" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search workflows" /><Button size="sm" type="submit">Search</Button></form>
        </div>
        <Async state={state} skeletonRows={8} empty={Object.assign((d) => !d.items.length, { element: <EmptyState title="No workflows match" hint="Adjust the filters or start a new procurement request." action={<Button size="sm" variant="primary" href="/functions/procurement">Start procurement</Button>} /> })}>
          {(d) => (
            <>
              <div className="overflow-x-auto"><table className="w-full min-w-[720px] text-left text-sm">
                <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500"><tr><th className="px-4 py-2 font-medium">Workflow</th><th className="px-3 py-2 font-medium">Status</th><th className="px-3 py-2 font-medium">Progress</th><th className="px-3 py-2 font-medium">Amount</th><th className="px-3 py-2 font-medium">Requester</th><th className="px-3 py-2 font-medium">Started</th></tr></thead>
                <tbody className="divide-y divide-slate-100">{d.items.map((w) => (
                  <tr key={w.id} className="hover:bg-slate-50">
                    <td className="px-4 py-2.5"><Link href={`/workflows/${w.id}`} className="block"><span className="font-mono text-[11px] text-slate-400">{w.ref}</span>{w.is_demo && <Badge tone="blue" className="ml-1.5">demo</Badge>}<div className="font-medium text-slate-900">{w.title}</div></Link></td>
                    <td className="px-3 py-2.5"><StatusBadge status={w.status} />{w.pending_approvals > 0 && <Badge tone="amber" className="ml-1">{w.pending_approvals} pending</Badge>}</td>
                    <td className="px-3 py-2.5"><div className="flex items-center gap-2"><div className="h-1.5 w-20 overflow-hidden rounded bg-slate-200"><div className={cn("h-full", w.status === "failed" ? "bg-red-500" : w.status === "completed" ? "bg-emerald-500" : "bg-accent-500")} style={{ width: `${(w.progress.done / w.progress.total) * 100}%` }} /></div><span className="tnum text-xs text-slate-500">{w.progress.done}/{w.progress.total}</span></div><div className="mt-0.5 text-[11px] text-slate-400">{w.status !== "completed" && w.current_step ? titleCase(w.current_step) : ""}</div></td>
                    <td className="tnum px-3 py-2.5">{inr(w.amount)}</td><td className="px-3 py-2.5 text-slate-600">{w.requester}</td><td className="px-3 py-2.5 text-xs text-slate-500">{relTime(w.created_at)}</td>
                  </tr>))}</tbody></table></div>
              <Pager page={d.page} pages={d.pages} total={d.total} onPage={setPage} />
            </>
          )}
        </Async>
      </Card>
    </>
  );
}

export default function Workflows() {
  return <Suspense><List /></Suspense>;
}
