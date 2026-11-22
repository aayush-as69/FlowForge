"use client";
import { useState } from "react";
import Link from "next/link";
import { useApi } from "@/lib/hooks";
import { Async, Card, EmptyState, PageHeader, Pager, Tabs } from "@/components/ui";
import ExceptionBlock from "@/components/ExceptionBlock";
import { relTime } from "@/lib/format";

const GROUPS = [["awaiting_review", "Awaiting review"], ["escalated", "Escalated"], ["failed", "Failed"], ["auto_resolved", "Automatically resolved"], ["resolved_by_human", "Resolved by humans"], ["all", "All"]];

export default function Exceptions() {
  const [group, setGroup] = useState("awaiting_review");
  const [page, setPage] = useState(1);
  const summary = useApi("/exceptions/summary", { interval: 6000 });
  const state = useApi(`/exceptions?group=${group}&page=${page}&page_size=12`, { interval: 6000 });
  const counts = summary.data || {};
  const total = Object.values(counts).reduce((a, b) => a + b, 0);
  return (
    <>
      <PageHeader title="Exceptions" subtitle="Exceptions never just stop a workflow: FlowForge classifies them, retries, searches alternatives and only then escalates to a person. Every step is recorded." />
      <Tabs value={group} onChange={(g) => { setGroup(g); setPage(1); }} tabs={GROUPS.map(([k, l]) => ({ key: k, label: l, count: k === "all" ? total : counts[k] }))} />
      <div className="mt-4">
        <Async state={state} skeletonRows={4} empty={Object.assign((d) => !d.items.length, { element: <Card><EmptyState title="No exceptions in this category" hint="That’s good news — or switch category to see how others were handled." /></Card> })}>
          {(d) => (
            <Card>
              <ul className="divide-y divide-slate-100">{d.items.map((e) => (
                <li key={e.id} className="p-4"><div className="mb-2 flex items-center justify-between gap-2 text-xs text-slate-500"><Link href={`/workflows/${e.workflow_id}`} className="font-medium text-accent-600 hover:underline">{e.workflow_ref} · {e.workflow_title}</Link><span>{relTime(e.detected_at)}</span></div><ExceptionBlock e={e} />
                  {["awaiting_review", "escalated"].includes(e.status) && <Link href="/approvals" className="mt-2 inline-block text-xs font-medium text-accent-600 hover:underline">Open in Approval center →</Link>}</li>
              ))}</ul>
              <Pager page={d.page} pages={d.pages} total={d.total} onPage={setPage} />
            </Card>
          )}
        </Async>
      </div>
    </>
  );
}
