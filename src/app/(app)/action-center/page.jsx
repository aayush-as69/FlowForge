"use client";
import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { ageLabel, filterItems } from "@/lib/action-center";
import { Async, Badge, Button, Card, EmptyState, PageHeader, Tabs } from "@/components/ui";

const TYPE = {
  approval: { label: "Approval", tone: "blue", href: () => "/approvals", action: "Review & decide" },
  exception: { label: "Exception", tone: "amber", href: (i) => `/workflows/${i.workflow_id}`, action: "Open workflow" },
  failed_workflow: { label: "Failed", tone: "red", href: (i) => `/workflows/${i.workflow_id}`, action: "Open workflow" },
};

function Row({ item, onRetry, busy }) {
  const t = TYPE[item.type];
  return (
    <li className="flex flex-wrap items-start gap-3 px-4 py-3">
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={t.tone}>{t.label}</Badge>
          <span className="text-sm font-medium text-slate-900">{item.title}</span>
          <span className="text-xs text-slate-500">{item.workflow_ref}</span>
          {item.overdue && <Badge tone="red">Overdue · {ageLabel(item.age_hours)}</Badge>}
          {!item.overdue && <span className="text-xs text-slate-500">waiting {ageLabel(item.age_hours)}</span>}
          {item.escalated && <Badge tone="amber">Escalated</Badge>}
        </div>
        <p className="mt-1 text-sm text-slate-600">{item.summary}</p>
        {item.blocked_reason && <p className="mt-1 text-xs text-slate-500">You can’t decide this: {item.blocked_reason}</p>}
      </div>
      <div className="flex shrink-0 gap-2">
        {item.type === "failed_workflow" && item.mine && <Button size="sm" loading={busy} onClick={() => onRetry(item)}>Retry</Button>}
        <Link href={t.href(item)} className="inline-flex h-8 items-center rounded-md border border-slate-300 px-3 text-sm text-slate-700 hover:bg-slate-50">{t.action}</Link>
      </div>
    </li>
  );
}

export default function ActionCenter() {
  const [tab, setTab] = useState("mine");
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  const state = useApi("/action-center", { interval: 8000 });
  const retry = async (item) => {
    setBusy(item.id); setError(null);
    try { await api(`/workflows/${item.workflow_id}/retry`, { method: "POST" }); await state.reload(); }
    catch (e) { setError(e.message); }
    finally { setBusy(null); }
  };
  const c = state.data?.counts;
  return (
    <>
      <PageHeader title="Action center" subtitle="Everything waiting on a person, in one place: approvals, exceptions that need review and failed automations. Overdue items come first." />
      <Tabs value={tab} onChange={setTab} tabs={[
        { key: "mine", label: "Needs me", count: c?.mine }, { key: "overdue", label: "Overdue", count: c?.overdue },
        { key: "approvals", label: "Approvals", count: c?.approvals }, { key: "exceptions", label: "Exceptions", count: c?.exceptions },
        { key: "failed", label: "Failed", count: c?.failed }, { key: "all", label: "All" },
      ]} />
      {error && <p role="alert" className="mt-3 text-sm text-red-600">{error}</p>}
      <div className="mt-4">
        <Async state={state} skeletonRows={4}>
          {(d) => {
            const items = filterItems(d.items, tab);
            return items.length === 0
              ? <Card><EmptyState title="All clear" hint="Nothing here needs a person right now." /></Card>
              : <Card><ul className="divide-y divide-slate-100">{items.map((i) => <Row key={`${i.type}-${i.id}`} item={i} onRetry={retry} busy={busy === i.id} />)}</ul></Card>;
          }}
        </Async>
      </div>
    </>
  );
}
