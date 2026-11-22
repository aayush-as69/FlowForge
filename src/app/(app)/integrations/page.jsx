"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { Async, Badge, Button, Card, Dot, PageHeader } from "@/components/ui";
import { relTime } from "@/lib/format";

function IntegrationCard({ i, canManage, onChange }) {
  const [busy, setBusy] = useState(null);
  const [error, setError] = useState(null);
  async function run(kind, body) {
    setBusy(kind); setError(null);
    try { await api(`/integrations/${i.key}${kind === "check" ? "/check" : ""}`, { method: kind === "check" ? "POST" : "PATCH", body }); await onChange(); }
    catch (e) { setError(e.message); } finally { setBusy(null); }
  }
  const tone = i.status === "connected" ? "green" : i.status === "degraded" ? "amber" : "red";
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between"><div><div className="flex items-center gap-2"><Dot tone={tone} pulse={i.status === "connected"} /><h2 className="text-sm font-semibold">{i.name}</h2></div><div className="mt-0.5 text-xs text-slate-500">{i.provider}</div></div><Badge tone={tone === "green" ? "green" : tone === "amber" ? "amber" : "red"}>{i.status === "connected" ? "● Connected" : i.status === "degraded" ? "Degraded" : "○ Disconnected"}</Badge></div>
      <p className="mt-2 text-sm text-slate-600">{i.description}</p>
      <div className="mt-2 flex flex-wrap gap-1">{i.capabilities.map((c) => <Badge key={c}>{c}</Badge>)}</div>
      <dl className="mt-3 grid grid-cols-3 gap-2 border-t border-slate-100 pt-3 text-center">
        <div><dd className="tnum text-sm font-semibold">{i.latency_ms ?? "—"}{i.latency_ms ? " ms" : ""}</dd><dt className="text-[11px] text-slate-500">latency</dt></div>
        <div><dd className="tnum text-sm font-semibold">{i.calls_total}</dd><dt className="text-[11px] text-slate-500">calls</dt></div>
        <div><dd className={`tnum text-sm font-semibold ${i.failures_total ? "text-red-600" : ""}`}>{i.failures_total}</dd><dt className="text-[11px] text-slate-500">failures</dt></div>
      </dl>
      <div className="mt-3 flex items-center justify-between gap-2"><span className="text-[11px] text-slate-400">Mode: {i.mode} adapter · checked {relTime(i.last_checked_at)}</span></div>
      {error && <div role="alert" className="mt-2 text-xs text-red-600">{error}</div>}
      {canManage && (
        <div className="mt-3 flex gap-2">
          <Button size="sm" loading={busy === "check"} onClick={() => run("check")}>Run health check</Button>
          {i.status === "disconnected" ? <Button size="sm" variant="primary" loading={busy === "patch"} onClick={() => run("patch", { status: "connected" })}>Reconnect</Button>
            : <Button size="sm" variant="danger" loading={busy === "patch"} onClick={() => { if (confirm(`Disconnect ${i.name}? Workflows that need it will raise exceptions.`)) run("patch", { status: "disconnected" }); }}>Disconnect</Button>}
        </div>
      )}
    </Card>
  );
}

export default function Integrations() {
  const { can } = useAuth();
  const state = useApi("/integrations", { interval: 8000 });
  return (
    <>
      <PageHeader title="Integrations" subtitle="Enterprise systems FlowForge acts through. The MVP uses realistic simulated adapters behind the same interface a live API would implement. Disconnect one to watch the exception engine respond." />
      <Async state={state} skeletonRows={4}>
        {(list) => <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{list.map((i) => <IntegrationCard key={i.key} i={i} canManage={can("integrations:manage")} onChange={state.reload} />)}</div>}
      </Async>
    </>
  );
}
