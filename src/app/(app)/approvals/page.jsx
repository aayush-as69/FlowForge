"use client";
import { useState } from "react";
import { useApi } from "@/lib/hooks";
import { Async, Card, EmptyState, PageHeader, Pager, Tabs } from "@/components/ui";
import ApprovalPanel from "@/components/ApprovalPanel";

export default function Approvals() {
  const [tab, setTab] = useState("pending");
  const [page, setPage] = useState(1);
  const state = useApi(`/approvals?status=${tab}&page=${page}&page_size=10`, { interval: 5000 });
  return (
    <>
      <PageHeader title="Approval center" subtitle="Human decisions FlowForge is waiting for. Each shows what happened, why, the relevant data and FlowForge’s recommendation. After you decide, the workflow resumes automatically." />
      <Tabs value={tab} onChange={(t) => { setTab(t); setPage(1); }} tabs={[{ key: "pending", label: "Needs a decision", count: state.data?.pending_total }, { key: "decided", label: "Decided" }]} />
      <div className="mt-4">
        <Async state={state} skeletonRows={4} empty={Object.assign((d) => !d.items.length, { element: <Card><EmptyState title={tab === "pending" ? "Nothing waiting on a human" : "No decisions recorded yet"} hint={tab === "pending" ? "FlowForge is handling everything on its own. Run a procurement demo to see an approval appear." : "Decided approvals appear here with who decided and why."} /></Card> })}>
          {(d) => (
            <div className="space-y-3">
              {d.items.map((a, i) => <ApprovalPanel key={a.id} approval={a} defaultOpen={tab === "pending" && i === 0} onDone={state.reload} />)}
              <Card><Pager page={d.page} pages={d.pages} total={d.total} onPage={setPage} /></Card>
            </div>
          )}
        </Async>
      </div>
    </>
  );
}
