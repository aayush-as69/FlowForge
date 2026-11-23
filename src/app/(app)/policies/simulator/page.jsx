"use client";
import { useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { Async, Badge, Button, Card, CardHeader, EmptyState, ErrorState, Field, PageHeader, inputCls } from "@/components/ui";
import { OUTCOME_LABELS, buildChanges, delta, editableFields } from "@/lib/simulator";
import { inr } from "@/lib/format";

function Results({ r }) {
  return (
    <Card>
      <CardHeader title="Result" subtitle={`Replayed ${r.replayed} past workflows${r.skipped ? ` (${r.skipped} skipped: they never reached a decision)` : ""}. Nothing was saved.`} />
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="text-left text-xs uppercase text-slate-500"><tr><th className="px-4 py-2">Outcome</th><th className="px-4 py-2">Current</th><th className="px-4 py-2">Proposed</th><th className="px-4 py-2">Change</th></tr></thead>
          <tbody className="divide-y divide-slate-100">
            {Object.keys(OUTCOME_LABELS).map((k) => (
              <tr key={k}><td className="px-4 py-2">{OUTCOME_LABELS[k]}</td><td className="tnum px-4 py-2">{r.current[k]}</td><td className="tnum px-4 py-2">{r.proposed[k]}</td><td className="tnum px-4 py-2 font-medium">{delta(r.current[k], r.proposed[k])}</td></tr>
            ))}
            <tr className="bg-slate-50 font-medium"><td className="px-4 py-2">Needs a person</td><td className="tnum px-4 py-2">{r.current.needs_human}</td><td className="tnum px-4 py-2">{r.proposed.needs_human}</td><td className="tnum px-4 py-2">{delta(r.current.needs_human, r.proposed.needs_human)}</td></tr>
          </tbody>
        </table>
      </div>
      <div className="border-t border-slate-100 p-4 text-sm text-slate-700">
        {r.human_workload_change_pct === null ? "No human workload in the sample to compare." : `Estimated human workload change: ${r.human_workload_change_pct > 0 ? "−" : r.human_workload_change_pct < 0 ? "+" : ""}${Math.abs(r.human_workload_change_pct)}%`}
        {r.changed_count > 0 && (
          <details className="mt-3"><summary className="cursor-pointer text-xs font-medium text-slate-600">{r.changed_count} workflow(s) would have gone differently</summary>
            <ul className="mt-2 space-y-1 text-xs">{r.changed.map((c) => <li key={c.workflow_id}><Link className="text-forge-700 hover:underline" href={`/workflows/${c.workflow_id}`}>{c.ref}</Link> {c.title} · {inr(c.amount)} · {OUTCOME_LABELS[c.before]} → <b>{OUTCOME_LABELS[c.after]}</b></li>)}</ul>
          </details>
        )}
      </div>
    </Card>
  );
}

export default function Simulator() {
  const { can } = useAuth();
  const state = useApi("/policies");
  const [draft, setDraft] = useState({});
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [sample, setSample] = useState("500");
  const [what, setWhat] = useState({ amount: "85000", category: "laptop", quantity: "1", budget: "100000" });
  const [one, setOne] = useState(null);

  if (!can("policies:write")) return <ErrorState error={Object.assign(new Error("Only administrators can use the policy simulator."), { status: 403 })} />;

  const run = async (extra) => {
    setBusy(true); setError(null);
    try { return await api("/policies/simulate", { method: "POST", body: extra }); }
    catch (e) { setError(e.message); return null; }
    finally { setBusy(false); }
  };

  return (
    <>
      <PageHeader title="Policy simulator" subtitle="Change a limit and see what it would have done to past requests, before touching the real policy. Nothing here is saved or executed."
        actions={<Link href="/policies" className="text-sm text-forge-700 hover:underline">Back to policies</Link>} />
      <Async state={state} skeletonRows={4} empty={Object.assign((d) => !d.length, { element: <EmptyState title="No policies" /> })}>
        {(policies) => {
          const changes = buildChanges(policies, draft);
          return (
            <div className="space-y-4">
              <Card>
                <CardHeader title="Proposed changes" subtitle="Edit any number; unchanged policies are ignored." />
                <ul className="divide-y divide-slate-100">
                  {policies.filter((p) => editableFields(p).length).map((p) => (
                    <li key={p.id} className="flex flex-wrap items-center gap-3 px-4 py-3">
                      <div className="min-w-0 flex-1"><div className="text-sm font-medium text-slate-900">{p.name}</div><div className="text-xs text-slate-500">{p.description}</div></div>
                      {editableFields(p).map((k) => (
                        <Field key={k} label={`${k.replaceAll("_", " ")} (now ${p.params[k]})`}>
                          <input className={inputCls} type="number" min="0" value={draft[p.id]?.[k] ?? p.params[k]}
                            onChange={(e) => setDraft((d) => ({ ...d, [p.id]: { ...d[p.id], [k]: e.target.value } }))} />
                        </Field>
                      ))}
                    </li>
                  ))}
                </ul>
                <div className="flex flex-wrap items-end gap-3 border-t border-slate-100 p-4">
                  <Field label="Past workflows to replay"><select className={inputCls} value={sample} onChange={(e) => setSample(e.target.value)}>{["100", "500", "1000"].map((n) => <option key={n}>{n}</option>)}</select></Field>
                  <Button variant="primary" loading={busy} disabled={changes.length === 0} onClick={async () => setResult(await run({ changes, sample: Number(sample) }))}>Test against history</Button>
                  <Button variant="ghost" onClick={() => { setDraft({}); setResult(null); setOne(null); }}>Reset</Button>
                  <span className="text-xs text-slate-500">{changes.length} change(s)</span>
                </div>
              </Card>
              {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
              {result && <Results r={result} />}
              <Card>
                <CardHeader title="Try one purchase" subtitle="See current versus proposed outcome for a single hypothetical order." />
                <div className="flex flex-wrap items-end gap-3 p-4">
                  {[["amount", "Total amount (₹)"], ["quantity", "Quantity"], ["budget", "Budget (₹)"]].map(([k, label]) => (
                    <Field key={k} label={label}><input className={inputCls} type="number" min="0" value={what[k]} onChange={(e) => setWhat((w) => ({ ...w, [k]: e.target.value }))} /></Field>
                  ))}
                  <Field label="Category"><input className={inputCls} value={what.category} onChange={(e) => setWhat((w) => ({ ...w, category: e.target.value }))} /></Field>
                  <Button loading={busy} onClick={async () => setOne(await run({ changes, purchase: { amount: Number(what.amount), quantity: Number(what.quantity), budget: Number(what.budget), category: what.category } }))}>Compare</Button>
                </div>
                {one && (
                  <div className="grid gap-px border-t border-slate-100 bg-slate-100 sm:grid-cols-2 [&>div]:bg-white [&>div]:p-4">
                    {[["Current policy", one.current], ["Proposed policy", one.proposed]].map(([title, o]) => (
                      <div key={title}><div className="text-xs font-semibold uppercase text-slate-500">{title}</div>
                        <div className="mt-1"><Badge tone={o.outcome === "auto" ? "green" : o.outcome === "blocked" ? "red" : "amber"}>{OUTCOME_LABELS[o.outcome]}</Badge></div>
                        <ul className="mt-2 list-disc pl-5 text-xs text-slate-600">{o.reasons.map((x, i) => <li key={i}>{x}</li>)}</ul></div>
                    ))}
                  </div>
                )}
              </Card>
            </div>
          );
        }}
      </Async>
    </>
  );
}
