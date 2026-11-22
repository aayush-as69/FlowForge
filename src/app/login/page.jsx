"use client";
import { Suspense, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import { safeNext } from "@/lib/safe-redirect.mjs";
import { Button, Field, inputCls } from "@/components/ui";

const ROLES = [
  { email: "admin@flowforge.demo", label: "Admin", hint: "Everything, incl. policy edits" },
  { email: "manager@flowforge.demo", label: "Manager", hint: "Approve Level 2 · manager sign-off" },
  { email: "approver@flowforge.demo", label: "Approver", hint: "Review exceptions" },
  { email: "requester@flowforge.demo", label: "Requester", hint: "Submit & track requests" },
  { email: "auditor@flowforge.demo", label: "Auditor", hint: "Read-only audit access" },
];

function LoginForm() {
  const router = useRouter();
  const next = safeNext(useSearchParams().get("next"));
  const [email, setEmail] = useState("admin@flowforge.demo");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api("/auth/login", { method: "POST", body: { email, password } });
      router.replace(next);
    } catch (err) {
      setError(err.message);
      setBusy(false);
    }
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_480px]">
      <div className="relative hidden flex-col justify-between bg-ink-900 p-10 text-white lg:flex">
        <Link href="/" className="flex items-center gap-2"><span className="grid size-8 place-items-center rounded-md bg-gradient-to-br from-accent-500 to-forge-500 font-bold">F</span><span className="text-lg font-semibold">FlowForge</span></Link>
        <div>
          <h1 className="max-w-md text-3xl font-semibold leading-tight tracking-tight">Automate the function. Not just the task.</h1>
          <p className="mt-4 max-w-md text-sm leading-relaxed text-slate-400">Sign in with a demo role to watch FlowForge take a procurement request from first input to verified outcome — and see exactly where humans decide.</p>
          <div className="mt-8 flex flex-wrap gap-1.5 text-[11px] text-slate-400">
            {["Input", "Understand", "Plan", "Decide", "Execute", "Verify", "Resolve", "Outcome"].map((s, i) => (
              <span key={s} className="flex items-center gap-1.5"><span className="rounded bg-white/10 px-2 py-1 text-slate-200">{s}</span>{i < 7 && <span>→</span>}</span>
            ))}
          </div>
        </div>
        <p className="text-xs text-slate-500">AI handles execution. Humans handle judgment.</p>
      </div>
      <div className="flex items-center justify-center p-6">
        <div className="w-full max-w-sm">
          <h2 className="text-xl font-semibold tracking-tight text-slate-900">Sign in</h2>
          <p className="mt-1 text-sm text-slate-500">Use a demo account. Password for all: <code className="rounded bg-slate-100 px-1 font-mono text-xs">flowforge-demo</code></p>
          <div className="mt-5 grid grid-cols-1 gap-1.5 sm:grid-cols-2">
            {ROLES.map((r) => (
              <button key={r.email} type="button" onClick={() => { setEmail(r.email); setPassword("flowforge-demo"); }}
                className={`rounded-md border px-3 py-2 text-left transition-colors ${email === r.email ? "border-accent-500 bg-accent-50" : "border-slate-200 bg-white hover:border-slate-300"}`}>
                <div className="text-sm font-medium text-slate-900">{r.label}</div>
                <div className="text-[11px] text-slate-500">{r.hint}</div>
              </button>
            ))}
          </div>
          <form onSubmit={submit} className="mt-5 space-y-3">
            <Field label="Email"><input className={inputCls} type="email" autoComplete="username" value={email} onChange={(e) => setEmail(e.target.value)} required /></Field>
            <Field label="Password"><input className={inputCls} type="password" autoComplete="current-password" value={password} onChange={(e) => setPassword(e.target.value)} required /></Field>
            {error && <div role="alert" className="rounded-md border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</div>}
            <Button type="submit" variant="primary" size="lg" className="w-full" loading={busy}>Sign in</Button>
          </form>
        </div>
      </div>
    </div>
  );
}

export default function LoginPage() {
  return <Suspense><LoginForm /></Suspense>;
}
