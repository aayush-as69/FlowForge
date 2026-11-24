"use client";
import { useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { Async, Badge, Button, Card, CardHeader, EmptyState, Field, PageHeader, inputCls } from "@/components/ui";
import { problemsOf, statusTone } from "@/lib/builder";

function RunBox({ def, onDone }) {
  const router = useRouter();
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const run = async () => {
    setBusy(true); setError(null);
    try { const wf = await api(`/builder/definitions/${def.id}/run`, { method: "POST", body: { text } }); onDone?.(); router.push(`/workflows/${wf.id}`); }
    catch (e) { setError(problemsOf(e)[0]); setBusy(false); }
  };
  return (
    <div className="mt-3 space-y-2 rounded-md bg-slate-50 p-3 ring-1 ring-inset ring-slate-200">
      <label className="block text-xs font-medium text-slate-600" htmlFor={`run-${def.id}`}>Request text</label>
      <textarea id={`run-${def.id}`} className={`${inputCls} h-20 py-2`} value={text} onChange={(e) => setText(e.target.value)} placeholder="e.g. Team offsite catering for 40 people, budget 48000" />
      {error && <p role="alert" className="text-xs text-red-700">{error}</p>}
      <Button variant="primary" size="sm" loading={busy} disabled={!text.trim()} onClick={run}>Start workflow</Button>
    </div>
  );
}

export default function BuilderHome() {
  const { can } = useAuth();
  const router = useRouter();
  const defs = useApi("/builder/definitions");
  const templates = useApi("/builder/templates");
  const [name, setName] = useState("");
  const [template, setTemplate] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [running, setRunning] = useState(null);
  const admin = can("policies:write");

  const create = async () => {
    setBusy(true); setError(null);
    try {
      const body = { name: name.trim(), ...(template ? { template_key: template } : {}) };
      const d = await api("/builder/definitions", { method: "POST", body });
      router.push(`/builder/${d.id}`);
    } catch (e) { setError(problemsOf(e)[0]); setBusy(false); }
  };

  return (
    <>
      <PageHeader title="Workflow Builder" subtitle="Compose governed workflows from audited building blocks: understand, check policy, ask a person, notify. Every version is tested before it can be published." />
      {admin && (
        <Card className="mb-4">
          <CardHeader title="Create a workflow" subtitle="Start blank or from a template. You can change everything afterwards." />
          <div className="grid gap-3 p-4 sm:grid-cols-[1fr_1fr_auto] sm:items-end">
            <Field label="Name"><input className={inputCls} value={name} onChange={(e) => setName(e.target.value)} placeholder="e.g. Travel expense approval" /></Field>
            <Field label="Start from">
              <select className={inputCls} value={template} onChange={(e) => setTemplate(e.target.value)}>
                <option value="">Blank workflow</option>
                {(templates.data || []).map((t) => <option key={t.key} value={t.key}>{t.name}</option>)}
              </select>
            </Field>
            <Button variant="primary" loading={busy} disabled={name.trim().length < 2} onClick={create}>Create draft</Button>
          </div>
          {error && <p role="alert" className="px-4 pb-3 text-xs text-red-700">{error}</p>}
        </Card>
      )}
      <Card className="mb-4">
        <CardHeader title="Your workflows" />
        <Async state={defs} empty={Object.assign((d) => !d.items.length, { element: <EmptyState title="No workflows yet" hint={admin ? "Create one above, starting from a template if you like." : "An administrator can create workflows."} /> })}>
          {(d) => (
            <ul className="divide-y divide-slate-100">
              {d.items.map((w) => (
                <li key={w.key} className="p-4">
                  <div className="flex flex-wrap items-center gap-2">
                    <Link href={`/builder/${w.id}`} className="font-medium text-forge-700 hover:underline">{w.name}</Link>
                    <Badge tone={statusTone(w.status)}>{w.status} · v{w.version}</Badge>
                    <span className="text-xs text-slate-500">{w.steps} steps · {w.tests} tests</span>
                    <span className="ml-auto flex gap-2">
                      {w.runnable && can("workflows:operate") && <Button size="sm" onClick={() => setRunning(running === w.id ? null : w.id)}>Run</Button>}
                      <Button size="sm" href={`/builder/${w.id}`}>{admin ? "Open" : "View"}</Button>
                    </span>
                  </div>
                  {w.description && <p className="mt-1 text-sm text-slate-600">{w.description}</p>}
                  {w.versions.length > 1 && <p className="mt-1 text-xs text-slate-500">Versions: {w.versions.map((v) => `v${v.version} ${v.status}`).join(" · ")}</p>}
                  {running === w.id && <RunBox def={w} />}
                </li>
              ))}
            </ul>
          )}
        </Async>
      </Card>
      <Card>
        <CardHeader title="Templates" subtitle="Each template comes with its own test cases." />
        <Async state={templates}>
          {(list) => (
            <ul className="grid gap-3 p-4 sm:grid-cols-2">
              {list.map((t) => (
                <li key={t.key} className="rounded-md p-3 ring-1 ring-inset ring-slate-200">
                  <div className="font-medium text-slate-900">{t.name}</div>
                  <p className="mt-0.5 text-sm text-slate-600">{t.description}</p>
                  <div className="mt-1 text-xs text-slate-500">{t.steps} steps · {t.tests} test cases</div>
                </li>
              ))}
            </ul>
          )}
        </Async>
      </Card>
    </>
  );
}
