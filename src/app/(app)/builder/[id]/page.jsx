"use client";
import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { Async, Badge, Button, Card, CardHeader, Field, PageHeader, inputCls } from "@/components/ui";
import {
  FIELDS, OUTCOMES, ROLES, STEP_TYPES, describeStep, moveStep, newStep, newTestCase, opsFor, patchCondition, patchStep,
  problemsOf, removeStep, statusTone,
} from "@/lib/builder";

const sel = `${inputCls} pr-7`;

function ConditionRow({ c, onChange, onRemove, disabled }) {
  const shown = Array.isArray(c.value) ? c.value.join(", ") : c.value ?? "";
  return (
    <div className="flex flex-wrap items-center gap-2">
      <select aria-label="Field" className={`${sel} w-40`} disabled={disabled} value={c.field} onChange={(e) => onChange({ field: e.target.value })}>{FIELDS.map((f) => <option key={f}>{f}</option>)}</select>
      <select aria-label="Operator" className={`${sel} w-28`} disabled={disabled} value={c.op} onChange={(e) => onChange({ op: e.target.value })}>{opsFor(c.field).map((o) => <option key={o}>{o}</option>)}</select>
      {c.op !== "exists" && <input aria-label="Value" className={`${inputCls} w-48`} disabled={disabled} value={shown} onChange={(e) => onChange({ value: e.target.value })} placeholder={c.op === "in" ? "a, b, c" : "value"} />}
      {!disabled && <button type="button" className="text-xs text-slate-500 hover:text-red-700" onClick={onRemove}>Remove</button>}
    </div>
  );
}

function StepCard({ step, index, count, onPatch, onMove, onRemove, disabled }) {
  return (
    <li className="rounded-md p-3 ring-1 ring-inset ring-slate-200">
      <div className="flex flex-wrap items-center gap-2">
        <span className="grid size-6 place-items-center rounded-full bg-slate-100 text-xs font-medium text-slate-600">{index + 1}</span>
        <Badge tone="slate">{STEP_TYPES[step.type]?.label || step.type}</Badge>
        <input aria-label={`Name of step ${index + 1}`} className={`${inputCls} max-w-xs flex-1`} disabled={disabled} value={step.name} onChange={(e) => onPatch({ name: e.target.value })} />
        {!disabled && (
          <span className="ml-auto flex gap-1">
            <Button size="sm" aria-label={`Move step ${index + 1} up`} disabled={index === 0} onClick={() => onMove(-1)}>↑</Button>
            <Button size="sm" aria-label={`Move step ${index + 1} down`} disabled={index === count - 1} onClick={() => onMove(1)}>↓</Button>
            <Button size="sm" aria-label={`Remove step ${index + 1}`} onClick={onRemove}>Remove</Button>
          </span>
        )}
      </div>
      <p className="mt-1.5 text-xs text-slate-500">{disabled ? describeStep(step) : STEP_TYPES[step.type]?.hint}</p>
      {!disabled && step.type === "rule" && (
        <div className="mt-3 space-y-2">
          {step.conditions.map((c, ci) => (
            <ConditionRow key={ci} c={c} disabled={disabled}
              onChange={(patch) => onPatch(patchCondition(step, ci, patch))}
              onRemove={() => onPatch({ conditions: step.conditions.filter((_, i) => i !== ci) })} />
          ))}
          <Button size="sm" onClick={() => onPatch({ conditions: [...step.conditions, { field: "amount", op: "<=", value: 0 }] })}>Add condition</Button>
          <div className="grid gap-2 sm:grid-cols-2">
            <Field label="If any condition fails">
              <select className={sel} value={step.on_fail} onChange={(e) => onPatch({ on_fail: e.target.value })}>
                <option value="approval">Flag the case for approval</option><option value="block">Block it and ask for a review</option>
              </select>
            </Field>
            <Field label="Message shown to reviewers"><input className={inputCls} value={step.message || ""} onChange={(e) => onPatch({ message: e.target.value })} /></Field>
          </div>
        </div>
      )}
      {!disabled && step.type === "approval" && (
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <Field label="Who must approve"><select className={sel} value={step.role} onChange={(e) => onPatch({ role: e.target.value })}>{ROLES.map((r) => <option key={r}>{r}</option>)}</select></Field>
          <Field label="When"><select className={sel} value={step.when || "always"} onChange={(e) => onPatch({ when: e.target.value })}><option value="always">Always</option><option value="flagged">Only if a rule flagged the case</option></select></Field>
        </div>
      )}
      {!disabled && step.type === "notify" && (
        <div className="mt-3"><Field label="Message" hint="Use {item}, {amount}, {quantity}… to include request details."><input className={inputCls} value={step.message || ""} onChange={(e) => onPatch({ message: e.target.value })} /></Field></div>
      )}
    </li>
  );
}

function Problems({ items }) {
  if (!items?.length) return null;
  return (
    <div role="alert" className="mb-4 rounded-md bg-red-50 p-3 text-sm text-red-800 ring-1 ring-inset ring-red-200">
      <div className="font-medium">Fix these before continuing:</div>
      <ul className="mt-1 list-disc pl-5">{items.map((p, i) => <li key={i}>{p}</li>)}</ul>
    </div>
  );
}

function TryIt({ steps }) {
  const [text, setText] = useState("Need 20 monitors for engineering, budget 80000");
  const [res, setRes] = useState(null);
  const [problems, setProblems] = useState(null);
  const [busy, setBusy] = useState(false);
  const go = async () => {
    setBusy(true); setProblems(null);
    try { setRes(await api("/builder/test", { method: "POST", body: { spec: { steps }, text } })); }
    catch (e) { setRes(null); setProblems(problemsOf(e)); }
    finally { setBusy(false); }
  };
  return (
    <Card>
      <CardHeader title="Try it" subtitle="Dry run with the current steps. Nothing is saved and nobody is asked." />
      <div className="space-y-3 p-4">
        <textarea aria-label="Test request" className={`${inputCls} h-16 py-2`} value={text} onChange={(e) => setText(e.target.value)} />
        <Button variant="primary" size="sm" loading={busy} disabled={!text.trim()} onClick={go}>Run test</Button>
        <Problems items={problems} />
        {res && (
          <div data-testid="dry-run">
            <div className="text-sm font-medium text-slate-900">Result: {OUTCOMES[res.outcome]}{res.role ? ` (${res.role})` : ""}</div>
            <ol className="mt-2 space-y-1 text-xs text-slate-700">
              {res.trace.map((t) => <li key={t.id}><b>{t.name}</b> — {t.result}: {t.detail}</li>)}
            </ol>
          </div>
        )}
      </div>
    </Card>
  );
}

function CaseEditor({ cases, onChange, results, disabled }) {
  const patch = (i, p) => onChange(cases.map((c, j) => (j === i ? { ...c, ...p } : c)));
  return (
    <Card>
      <CardHeader title="Test cases" subtitle="Describe a request and what should happen. All cases must pass before this version can be published." />
      <div className="space-y-3 p-4">
        {cases.map((c, i) => {
          const r = results?.results?.find((x) => x.name === c.name);
          return (
            <div key={i} className="rounded-md p-3 ring-1 ring-inset ring-slate-200">
              <div className="flex flex-wrap items-center gap-2">
                <input aria-label={`Name of case ${i + 1}`} className={`${inputCls} max-w-xs`} disabled={disabled} value={c.name} onChange={(e) => patch(i, { name: e.target.value })} />
                {r && <Badge tone={r.passed ? "green" : "red"}>{r.passed ? "passing" : "failing"}</Badge>}
                {!disabled && <button type="button" className="ml-auto text-xs text-slate-500 hover:text-red-700" onClick={() => onChange(cases.filter((_, j) => j !== i))}>Remove</button>}
              </div>
              <div className="mt-2 grid gap-2 sm:grid-cols-3">
                <Field label="Amount"><input aria-label={`Amount for case ${i + 1}`} className={inputCls} disabled={disabled} value={c.fields?.amount ?? ""} onChange={(e) => patch(i, { fields: { ...(c.fields || {}), ...(e.target.value === "" ? { amount: undefined } : { amount: Number(e.target.value) || 0 }) } })} /></Field>
                <Field label="Expected outcome">
                  <select aria-label={`Expected outcome for case ${i + 1}`} className={sel} disabled={disabled} value={c.expect.outcome} onChange={(e) => patch(i, { expect: { outcome: e.target.value, ...(e.target.value === "approval" && c.expect.role ? { role: c.expect.role } : {}) } })}>
                    {Object.entries(OUTCOMES).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
                  </select>
                </Field>
                {c.expect.outcome === "approval" && (
                  <Field label="Approver role"><select className={sel} disabled={disabled} value={c.expect.role || ""} onChange={(e) => patch(i, { expect: { outcome: "approval", ...(e.target.value ? { role: e.target.value } : {}) } })}><option value="">any</option>{ROLES.map((x) => <option key={x}>{x}</option>)}</select></Field>
                )}
              </div>
              {r && !r.passed && <p className="mt-2 text-xs text-red-700">Expected {r.expected}, got {r.actual}.</p>}
            </div>
          );
        })}
        {!disabled && <Button size="sm" onClick={() => onChange([...cases, newTestCase(cases.length + 1)])}>Add test case</Button>}
      </div>
    </Card>
  );
}

function Editor({ def, reload }) {
  const { can } = useAuth();
  const router = useRouter();
  const [draft, setDraft] = useState({ name: def.name, description: def.description, steps: def.spec.steps, tests: def.test_cases });
  const [dirty, setDirty] = useState(false);
  const [problems, setProblems] = useState(null);
  const [results, setResults] = useState(null);
  const [busy, setBusy] = useState(null);
  const [notice, setNotice] = useState(null);
  const editable = can("policies:write") && def.status === "draft";
  const change = (patch) => { setDraft((d) => ({ ...d, ...patch })); setDirty(true); setNotice(null); };

  const act = async (label, fn) => {
    setBusy(label); setProblems(null); setNotice(null);
    try { await fn(); } catch (e) { setProblems(problemsOf(e)); } finally { setBusy(null); }
  };
  const save = () => act("save", async () => {
    await api(`/builder/definitions/${def.id}`, { method: "PUT", body: { name: draft.name, description: draft.description, spec: { steps: draft.steps }, tests: draft.tests } });
    setDirty(false); setNotice("Saved."); reload();
  });
  const runTests = () => act("tests", async () => { setResults(await api(`/builder/definitions/${def.id}/tests/run`, { method: "POST" })); });
  const publish = () => act("publish", async () => { await api(`/builder/definitions/${def.id}/publish`, { method: "POST" }); setNotice("Published."); reload(); });
  const version = () => act("version", async () => { const v = await api(`/builder/definitions/${def.id}/new-version`, { method: "POST" }); router.push(`/builder/${v.id}`); });
  const addStep = (type) => change({ steps: [...draft.steps, newStep(type, draft.steps)] });

  return (
    <>
      <PageHeader eyebrow={<Link href="/builder" className="hover:underline">← Workflow Builder</Link>} title={def.name}
        subtitle={<span className="inline-flex items-center gap-2"><Badge tone={statusTone(def.status)}>{def.status} · v{def.version}</Badge>{def.status !== "draft" && "Published versions are read-only. Create a new version to change it."}</span>}
        actions={<>
          {def.status !== "draft" && can("policies:write") && <Button loading={busy === "version"} onClick={version}>Create new version</Button>}
          {editable && <Button loading={busy === "save"} disabled={!dirty} onClick={save}>Save draft</Button>}
          {editable && <Button loading={busy === "tests"} disabled={dirty} onClick={runTests}>Run tests</Button>}
          {editable && <Button variant="primary" loading={busy === "publish"} disabled={dirty} onClick={publish}>Publish</Button>}
        </>} />
      <Problems items={problems} />
      {notice && <p role="status" className="mb-3 text-sm text-green-700">{notice}</p>}
      {results && <p role="status" className="mb-3 text-sm text-slate-700">Tests: {results.passed} of {results.total} passing{results.failed ? ` · ${results.failed} failing` : ""}.</p>}
      {editable && dirty && <p className="mb-3 text-xs text-slate-500">You have unsaved changes. Save before running tests or publishing.</p>}
      <div className="grid gap-4 lg:grid-cols-[1.4fr_1fr]">
        <div className="space-y-4">
          <Card>
            <CardHeader title="Steps" subtitle="Steps run top to bottom. A person is only asked when a step says so." />
            <div className="space-y-3 p-4">
              {editable && (
                <div className="grid gap-2 sm:grid-cols-2">
                  <Field label="Name"><input className={inputCls} value={draft.name} onChange={(e) => change({ name: e.target.value })} /></Field>
                  <Field label="Description"><input className={inputCls} value={draft.description} onChange={(e) => change({ description: e.target.value })} /></Field>
                </div>
              )}
              <ol className="space-y-3">
                {draft.steps.map((s, i) => (
                  <StepCard key={s.id} step={s} index={i} count={draft.steps.length} disabled={!editable}
                    onPatch={(p) => change({ steps: patchStep(draft.steps, i, p) })}
                    onMove={(d) => change({ steps: moveStep(draft.steps, i, d) })}
                    onRemove={() => change({ steps: removeStep(draft.steps, i) })} />
                ))}
              </ol>
              {editable && (
                <div className="flex flex-wrap gap-2 pt-1">
                  {["rule", "approval", "notify"].map((t) => <Button key={t} size="sm" onClick={() => addStep(t)}>+ {STEP_TYPES[t].label}</Button>)}
                </div>
              )}
            </div>
          </Card>
          <CaseEditor cases={draft.tests} results={results} disabled={!editable} onChange={(tests) => change({ tests })} />
        </div>
        <div className="space-y-4">
          <TryIt steps={draft.steps} />
        </div>
      </div>
    </>
  );
}

export default function BuilderEditor() {
  const { id } = useParams();
  const state = useApi(`/builder/definitions/${id}`);
  return <Async state={state}>{(def) => <Editor key={`${def.id}-${def.status}-${def.published_at}`} def={def} reload={state.reload} />}</Async>;
}
