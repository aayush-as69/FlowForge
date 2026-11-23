"use client";
import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { Async, Badge, Button, Card, PageHeader, cn, inputCls } from "@/components/ui";
import { fmtDateTime, inr, titleCase } from "@/lib/format";

const ORDER = ["budget", "category", "approval", "documentation", "organization", "vendor", "decision", "exception"];
const MONEY = ["amount", "max_amount", "min_amount"];

function summarize(p) {
  const x = p.params;
  if (x.categories) return x.categories.join(", ");
  if (x.max_amount !== undefined) return `≤ ${inr(x.max_amount)}`;
  if (x.min_amount !== undefined) return `≥ ${inr(x.min_amount)}`;
  if (x.amount !== undefined) return `≥ ${inr(x.amount)} → ${x.role}`;
  if (x.threshold_pct !== undefined) return `> ${x.threshold_pct}% above historical average`;
  if (x.max_quantity !== undefined) return `max ${x.max_quantity} units`;
  if (x.fields) return `requires ${x.fields.join(", ")}`;
  if (x.min !== undefined) return `minimum ${x.min}`;
  if (x.weights) return Object.entries(x.weights).map(([k, v]) => `${k} ${v}`).join(" · ");
  return "—";
}

function Editor({ p, onSaved, onCancel }) {
  const [params, setParams] = useState(p.params);
  const [severity, setSeverity] = useState(p.severity);
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);
  const setKey = (k, v) => setParams((s) => ({ ...s, [k]: v }));
  async function save() {
    setBusy(true); setError(null);
    try { await api(`/policies/${p.id}`, { method: "PATCH", body: { params, severity } }); await onSaved(); } catch (e) { setError(e.message); setBusy(false); }
  }
  return (
    <div className="mt-3 space-y-3 rounded-md bg-slate-50 p-3">
      <div className="grid gap-3 sm:grid-cols-2">
        {Object.entries(params).map(([k, v]) => (
          <label key={k} className={cn("block", typeof v === "object" && !Array.isArray(v) && "sm:col-span-2")}>
            <span className="mb-1 block text-xs font-medium text-slate-700">{titleCase(k)}{MONEY.includes(k) && typeof v === "number" ? ` — ${inr(v)}` : ""}</span>
            {typeof v === "number" ? <input className={inputCls} type="number" step="any" value={v} onChange={(e) => setKey(k, e.target.value === "" ? 0 : Number(e.target.value))} />
              : Array.isArray(v) ? <input className={inputCls} value={v.join(", ")} onChange={(e) => setKey(k, e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />
              : k === "role" ? <select className={inputCls} value={v} onChange={(e) => setKey(k, e.target.value)}>{["approver", "manager", "admin"].map((r) => <option key={r}>{r}</option>)}</select>
              : typeof v === "object" ? <div className="grid grid-cols-3 gap-2">{Object.entries(v).map(([wk, wv]) => <label key={wk} className="text-[11px] text-slate-500">{wk}<input className={inputCls} type="number" step="0.05" value={wv} onChange={(e) => setKey(k, { ...v, [wk]: Number(e.target.value) })} /></label>)}</div>
              : <input className={inputCls} value={v} onChange={(e) => setKey(k, e.target.value)} />}
          </label>
        ))}
        <label className="block"><span className="mb-1 block text-xs font-medium text-slate-700">Enforcement</span><select className={inputCls} value={severity} onChange={(e) => setSeverity(e.target.value)}><option value="block">Block (hard stop → human override)</option><option value="warn">Warn (flag for review)</option></select></label>
      </div>
      {error && <div role="alert" className="text-xs text-red-600">{error}</div>}
      <div className="flex gap-2"><Button size="sm" variant="primary" loading={busy} onClick={save}>Save policy</Button><Button size="sm" variant="ghost" onClick={onCancel}>Cancel</Button></div>
    </div>
  );
}

export default function Policies() {
  const { can } = useAuth();
  const state = useApi("/policies");
  const [editing, setEditing] = useState(null);
  const [error, setError] = useState(null);
  async function toggle(p) {
    setError(null);
    try { await api(`/policies/${p.id}`, { method: "PATCH", body: { enabled: !p.enabled } }); await state.reload(); } catch (e) { setError(e.message); }
  }
  return (
    <>
      <PageHeader title="Policies & decision rules" subtitle="Business rules are data, not code. Changes take effect for the next workflow step that evaluates them and are recorded in the audit trail."
        actions={can("policies:write") && <Link href="/policies/simulator" className="inline-flex h-9 items-center rounded-md border border-slate-300 bg-white px-3.5 text-sm font-medium text-slate-700 hover:bg-slate-50">Try changes in the simulator</Link>} />
      {!can("policies:write") && <div className="mb-3 rounded-md bg-slate-100 px-3 py-2 text-xs text-slate-600">Read-only: only administrators can modify policies.</div>}
      {error && <div role="alert" className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      <Async state={state} skeletonRows={6}>
        {(list) => (
          <div className="space-y-4">
            {ORDER.map((cat) => {
              const items = list.filter((p) => p.category === cat);
              if (!items.length) return null;
              return (
                <Card key={cat}>
                  <div className="border-b border-slate-100 px-4 py-2.5 text-xs font-semibold uppercase tracking-wide text-slate-500">{cat === "decision" ? "Decision engine (autonomy levels)" : cat === "exception" ? "Exception engine" : titleCase(cat)}</div>
                  <ul className="divide-y divide-slate-100">{items.map((p) => (
                    <li key={p.id} className={cn("px-4 py-3", !p.enabled && "opacity-60")}>
                      <div className="flex flex-wrap items-start justify-between gap-2">
                        <div className="min-w-0"><div className="flex flex-wrap items-center gap-1.5"><span className="text-sm font-semibold">{p.name}</span><Badge tone={p.severity === "block" ? "red" : "amber"}>{p.severity}</Badge><span className="text-[11px] text-slate-400">v{p.version}{p.updated_by ? ` · ${p.updated_by} · ${fmtDateTime(p.updated_at)}` : ""}</span></div>
                          <p className="mt-0.5 text-xs text-slate-500">{p.description}</p><div className="mt-1 font-mono text-xs text-slate-700">{summarize(p)}</div></div>
                        {can("policies:write") && <div className="flex gap-1.5"><Button size="sm" onClick={() => setEditing(editing === p.id ? null : p.id)}>Edit</Button><Button size="sm" variant="ghost" onClick={() => toggle(p)}>{p.enabled ? "Disable" : "Enable"}</Button></div>}
                      </div>
                      {editing === p.id && <Editor p={p} onCancel={() => setEditing(null)} onSaved={async () => { setEditing(null); await state.reload(); }} />}
                    </li>))}</ul>
                </Card>
              );
            })}
          </div>
        )}
      </Async>
    </>
  );
}
