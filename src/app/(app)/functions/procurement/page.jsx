"use client";
import { useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { Async, Badge, Button, Card, CardHeader, Field, PageHeader, Tabs, cn, inputCls } from "@/components/ui";
import { inr } from "@/lib/format";

const CATEGORIES = ["laptop", "monitor", "peripherals", "furniture", "software", "networking", "server"];
const EXAMPLE = "I need a laptop for a new employee joining next Monday. Budget is ₹1,00,000.";

function ConfidenceBar({ value }) {
  const pct = Math.round(value * 100);
  return <div className="flex items-center gap-2"><div className="h-1.5 w-24 overflow-hidden rounded bg-slate-200"><div className={cn("h-full", pct >= 80 ? "bg-emerald-500" : pct >= 60 ? "bg-amber-500" : "bg-red-500")} style={{ width: `${pct}%` }} /></div><span className="tnum text-xs text-slate-600">{pct}%</span></div>;
}

function Review({ req, onExecuted }) {
  const [draft, setDraft] = useState({
    item: req.item || "", category: req.category || "", quantity: req.quantity ?? "", purpose: req.purpose || "",
    required_date: req.required_date || "", budget: req.budget ?? "", requirements: req.requirements || "",
  });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const set = (k) => (e) => setDraft((d) => ({ ...d, [k]: e.target.value }));
  const dirty = useMemo(() => Object.entries(draft).some(([k, v]) => String(v ?? "") !== String(req[k] ?? "")), [draft, req]);
  const missing = ["category", "quantity", "budget"].filter((k) => !draft[k]);

  async function execute() {
    setBusy(true); setError(null);
    try {
      if (dirty) {
        const patch = {
          item: draft.item || null, category: draft.category || null, quantity: draft.quantity ? Number(draft.quantity) : null,
          purpose: draft.purpose || null, required_date: draft.required_date || null, budget: draft.budget !== "" ? Number(draft.budget) : null,
          requirements: draft.requirements || null,
        };
        if (draft.required_date !== (req.required_date || "")) patch.required_date_text = draft.required_date || null;
        await api(`/requests/${req.id}`, { method: "PATCH", body: patch });
      }
      const res = await api(`/requests/${req.id}/execute`, { method: "POST" });
      onExecuted(res.workflow_id);
    } catch (e) {
      setError(e.errors?.length ? e.errors.map((x) => `${x.field}: ${x.message}`).join("; ") : e.message);
      setBusy(false);
    }
  }

  return (
    <Card className="ff-enter border-accent-500/40">
      <CardHeader title="2 · FlowForge understood your request" subtitle="Inspect and correct before execution." action={<div className="flex items-center gap-2 text-xs text-slate-500">Confidence <ConfidenceBar value={req.confidence} /><Badge tone="blue">{req.extraction_engine}</Badge></div>} />
      <div className="space-y-4 p-4">
        {req.extraction_notes?.length > 0 && <ul className="rounded-md bg-amber-50 px-3 py-2 text-xs text-amber-900">{req.extraction_notes.map((n) => <li key={n}>• {n}</li>)}</ul>}
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Request type / category" error={!draft.category && "Required"}><select className={inputCls} value={draft.category} onChange={set("category")}><option value="">Select…</option>{CATEGORIES.map((c) => <option key={c}>{c}</option>)}</select></Field>
          <Field label="Item"><input className={inputCls} value={draft.item} onChange={set("item")} /></Field>
          <Field label="Quantity" error={!draft.quantity && "Required"}><input className={inputCls} type="number" min="1" max="1000" value={draft.quantity} onChange={set("quantity")} /></Field>
          <Field label={`Budget (INR)${draft.budget ? ` — ${inr(Number(draft.budget))}` : ""}`} error={!draft.budget && "Required"}><input className={inputCls} type="number" min="0" value={draft.budget} onChange={set("budget")} /></Field>
          <Field label={`Required date${req.required_date_text ? ` (“${req.required_date_text}”)` : ""}`}><input className={inputCls} type="date" value={draft.required_date} onChange={set("required_date")} /></Field>
          <Field label="Purpose"><input className={inputCls} value={draft.purpose} onChange={set("purpose")} /></Field>
          <div className="sm:col-span-2"><Field label="Additional requirements"><input className={inputCls} value={draft.requirements} onChange={set("requirements")} /></Field></div>
        </div>
        {req.demo_faults?.length > 0 && <div className="text-xs text-slate-500">Simulation enabled: {req.demo_faults.join(", ")}</div>}
        {error && <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}
        <div className="flex flex-wrap items-center gap-3">
          <Button variant="primary" size="lg" disabled={missing.length > 0} loading={busy} onClick={execute}>{dirty ? "Save corrections & execute" : "Confirm & execute"} →</Button>
          {dirty && <Badge tone="violet">edited — corrections are audited</Badge>}
          {missing.length > 0 && <span className="text-xs text-red-600">Complete: {missing.join(", ")}</span>}
        </div>
      </div>
    </Card>
  );
}

export default function Procurement() {
  const router = useRouter();
  const { can } = useAuth();
  const [tab, setTab] = useState("text");
  const [text, setText] = useState(EXAMPLE);
  const [email, setEmail] = useState({ from: "Ananya Rao <ananya.rao@meridian.example>", subject: "Laptop for new joiner", body: "Hi team,\n\nPlease arrange a laptop (16GB RAM) for a new employee joining next Monday.\nBudget is ₹1,00,000.\n\nThanks" });
  const [form, setForm] = useState({ item: "Laptop", purpose: "New employee", quantity: 1, required_date_text: "next Monday", budget: 100000, requirements: "" });
  const [faults, setFaults] = useState([]);
  const [req, setReq] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const [demoBusy, setDemoBusy] = useState(null);
  const demo = can("demo:run");
  const scenarios = useApi(demo ? "/functions/procurement/scenarios" : null);
  const writable = can("requests:create");

  async function understand() {
    setBusy(true); setError(null); setReq(null);
    let body;
    if (tab === "text" || tab === "api") body = { source: tab, text };
    else if (tab === "email") body = { source: "email", text: `Subject: ${email.subject}\nFrom: ${email.from}\n\n${email.body}` };
    else body = { source: "web_form", fields: { ...form, quantity: form.quantity ? Number(form.quantity) : null, budget: form.budget !== "" ? Number(form.budget) : null, requirements: form.requirements || null, required_date_text: form.required_date_text || null } };
    body.demo_faults = demo ? faults : [];
    try { setReq(await api("/requests", { method: "POST", body })); }
    catch (e) { setError(e.errors?.length ? e.errors.map((x) => `${x.field}: ${x.message}`).join("; ") : e.message); }
    finally { setBusy(false); }
  }

  async function runDemo(key) {
    setDemoBusy(key); setError(null);
    try { const r = await api("/functions/procurement/demo", { method: "POST", body: { scenario: key } }); router.push(`/workflows/${r.workflow_id}`); }
    catch (e) { setError(e.message); setDemoBusy(null); }
  }

  const toggle = (f) => setFaults((x) => (x.includes(f) ? x.filter((y) => y !== f) : [...x, f]));
  const curl = `curl -X POST $FLOWFORGE_URL/api/requests \\\n  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \\\n  -d '${JSON.stringify({ source: "api", text }).replace(/'/g, "'\\''")}'`;

  return (
    <>
      <PageHeader eyebrow="Business function" title="Procurement" subtitle="Submit a request in any form. FlowForge understands it, validates policy, evaluates vendors, decides, executes and verifies — asking a human only when judgment is needed."
        actions={demo && <Button variant="primary" loading={demoBusy === "laptop_primary"} onClick={() => runDemo("laptop_primary")}>▶ Run the primary demo</Button>} />
      {error && <div role="alert" className="mb-4 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      <div className={cn("grid gap-4", demo && "xl:grid-cols-[1fr_380px]")}>
        <div className="space-y-4">
          <Card>
            <CardHeader title="1 · Ingest" subtitle="Web form, free text, email-style or API" />
            {!writable ? <div className="p-4 text-sm text-slate-600">Your role ({"read-only"}) cannot submit requests. Switch to a requester, approver, manager or admin account.</div> : (
              <>
                <Tabs value={tab} onChange={setTab} tabs={[{ key: "text", label: "Text" }, { key: "email", label: "Email" }, { key: "form", label: "Web form" }, { key: "api", label: "API" }]} />
                <div className="space-y-3 p-4">
                  {tab === "text" && <Field label="Describe what you need"><textarea className={cn(inputCls, "h-28 py-2")} value={text} onChange={(e) => setText(e.target.value)} /></Field>}
                  {tab === "email" && <div className="space-y-2"><Field label="From"><input className={inputCls} value={email.from} onChange={(e) => setEmail({ ...email, from: e.target.value })} /></Field><Field label="Subject"><input className={inputCls} value={email.subject} onChange={(e) => setEmail({ ...email, subject: e.target.value })} /></Field><Field label="Message"><textarea className={cn(inputCls, "h-28 py-2")} value={email.body} onChange={(e) => setEmail({ ...email, body: e.target.value })} /></Field></div>}
                  {tab === "form" && (
                    <div className="grid gap-3 sm:grid-cols-2">
                      <Field label="Item"><input className={inputCls} value={form.item} onChange={(e) => setForm({ ...form, item: e.target.value })} /></Field>
                      <Field label="Purpose"><input className={inputCls} value={form.purpose} onChange={(e) => setForm({ ...form, purpose: e.target.value })} /></Field>
                      <Field label="Quantity"><input className={inputCls} type="number" min="1" value={form.quantity} onChange={(e) => setForm({ ...form, quantity: e.target.value })} /></Field>
                      <Field label="Required date" hint="e.g. next Monday, 12 Dec, in 5 days"><input className={inputCls} value={form.required_date_text} onChange={(e) => setForm({ ...form, required_date_text: e.target.value })} /></Field>
                      <Field label="Budget (INR)"><input className={inputCls} type="number" min="0" value={form.budget} onChange={(e) => setForm({ ...form, budget: e.target.value })} /></Field>
                      <Field label="Additional requirements"><input className={inputCls} value={form.requirements} onChange={(e) => setForm({ ...form, requirements: e.target.value })} /></Field>
                    </div>
                  )}
                  {tab === "api" && (
                    <div className="space-y-2">
                      <Field label="Request text sent by your system"><textarea className={cn(inputCls, "h-20 py-2")} value={text} onChange={(e) => setText(e.target.value)} /></Field>
                      <div className="text-xs font-medium text-slate-600">Equivalent call — <code className="font-mono">POST /api/requests</code> (cookie session or Bearer token):</div>
                      <pre className="overflow-x-auto rounded-md bg-ink-900 p-3 font-mono text-[11px] leading-relaxed text-slate-200">{curl}</pre>
                      <p className="text-xs text-slate-500">Interactive API docs: <a className="text-accent-600 underline" href="/api/docs" target="_blank">/api/docs</a></p>
                    </div>
                  )}
                  {demo && <details className="text-xs"><summary className="cursor-pointer font-medium text-slate-600">Demo simulation options</summary>
                    <div className="mt-2 space-y-1.5 rounded-md bg-slate-50 p-3">
                      {[["erp_timeout", "ERP times out on first PO posting (tests automatic retry)"], ["vendor_unavailable", "Selected vendor reports an outage (tests alternative search)"], ["invoice_mismatch", "Invoice mismatch at verification (tests failure + operator retry)"]].map(([k, l]) => (
                        <label key={k} className="flex items-start gap-2"><input type="checkbox" className="mt-0.5" checked={faults.includes(k)} onChange={() => toggle(k)} /><span><span className="font-mono">{k}</span> — {l}</span></label>
                      ))}
                    </div></details>}
                  <Button variant="primary" loading={busy} onClick={understand}>Understand request →</Button>
                </div>
              </>
            )}
          </Card>
          {req && <Review key={req.id} req={req} onExecuted={(id) => router.push(`/workflows/${id}`)} />}
        </div>
        {demo && <Card className="h-fit">
          <CardHeader title="Guided demo scenarios" subtitle="Each runs the real workflow engine end to end" />
          <Async state={scenarios} skeletonRows={4}>
            {(list) => (
              <ul className="divide-y divide-slate-100">
                {list.map((s, i) => (
                  <li key={s.key} className="p-4">
                    <div className="flex items-start justify-between gap-2"><div className="text-sm font-medium text-slate-900">{s.label}</div>{i === 0 && <Badge tone="blue">Primary</Badge>}</div>
                    <p className="mt-1 text-xs italic text-slate-500">“{s.text}”</p>
                    <div className="mt-2 flex flex-wrap gap-1">{s.shows.map((x) => <Badge key={x}>{x}</Badge>)}</div>
                    <Button className="mt-3" size="sm" variant={i === 0 ? "primary" : "secondary"} disabled={!writable} loading={demoBusy === s.key} onClick={() => runDemo(s.key)}>▶ Run scenario</Button>
                  </li>
                ))}
              </ul>
            )}
          </Async>
          <div className="border-t border-slate-100 p-4 text-xs text-slate-500">Approvals need a <b>manager</b> or <b>approver</b> account. Sign in as one in another browser window to decide while the demo is paused — or as <b>admin</b> to do everything.</div>
        </Card>}
      </div>
    </>
  );
}
