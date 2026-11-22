import Link from "next/link";

const STAGES = ["Input", "Understand", "Plan", "Decide", "Execute", "Verify", "Resolve", "Outcome"];

const EXAMPLE = [
  ["Understand", "AI extracts: Laptop · qty 1 · new employee · next Monday · ₹1,00,000", "auto"],
  ["Policy check", "Category allowed ✓  Budget within limit ✓  New hire verified in HR ✓  Manager approval required ⚠", "auto"],
  ["Vendor evaluation", "5 vendors compared on price, delivery, rating, warranty, reliability. Bluepeak recommended.", "auto"],
  ["Exception", "Bluepeak is 18% above its historical average. No safe alternative found.", "exception"],
  ["Human review", "Reviewer sees what happened, why, the recommendation and options — approves.", "human"],
  ["Purchase order", "PO issued, posted to ERP (timeout retried automatically), spend committed.", "auto"],
  ["Verification", "Delivery date, budget and invoice three-way match verified. Outcome recorded.", "auto"],
];

const LEVELS = [
  ["Level 1", "Auto-execute", "Routine, low-risk work. Invoice matches the PO; order within limits with an approved vendor. FlowForge proceeds and records why.", "bg-emerald-500"],
  ["Level 2", "Review", "Ambiguous or unusual. A quote 18% above historical average pauses the workflow and asks a reviewer — with context and a recommendation.", "bg-amber-500"],
  ["Level 3", "Human decision", "High-impact, accountable decisions. The human decides with a written justification; the workflow then continues on its own.", "bg-forge-500"],
];

export default function Landing() {
  return (
    <div className="bg-white text-slate-900">
      <header className="sticky top-0 z-30 border-b border-slate-200/70 bg-white/85 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-5">
          <div className="flex items-center gap-2"><span className="grid size-7 place-items-center rounded-md bg-gradient-to-br from-accent-500 to-forge-500 text-sm font-bold text-white">F</span><span className="font-semibold tracking-tight">FlowForge</span></div>
          <nav className="hidden items-center gap-6 text-sm text-slate-600 md:flex">
            <a href="#gap" className="hover:text-slate-900">The gap</a><a href="#example" className="hover:text-slate-900">Procurement</a><a href="#control" className="hover:text-slate-900">Human control</a><a href="#benefits" className="hover:text-slate-900">Benefits</a>
          </nav>
          <Link href="/login" className="rounded-md bg-ink-900 px-3.5 py-1.5 text-sm font-medium text-white hover:bg-ink-800">Open the product</Link>
        </div>
      </header>

      <section className="border-b border-slate-200 bg-gradient-to-b from-slate-50 to-white">
        <div className="mx-auto max-w-6xl px-5 pb-14 pt-16 md:pt-24">
          <div className="text-xs font-semibold uppercase tracking-[0.18em] text-accent-600">FlowForge</div>
          <h1 className="mt-3 max-w-3xl text-4xl font-semibold leading-[1.08] tracking-tight md:text-6xl">Automate the function. <span className="text-slate-400">Not just the task.</span></h1>
          <p className="mt-5 max-w-2xl text-lg leading-relaxed text-slate-600">AI-native automation that takes business functions from the first input to the finished outcome, while humans handle only the decisions that require judgment.</p>
          <div className="mt-8 flex flex-wrap gap-3">
            <Link href="/login" className="rounded-md bg-accent-600 px-5 py-3 text-sm font-semibold text-white shadow-sm hover:bg-accent-700">Run the procurement demo →</Link>
            <a href="#gap" className="rounded-md px-5 py-3 text-sm font-semibold text-slate-700 ring-1 ring-inset ring-slate-300 hover:bg-slate-50">See the difference</a>
          </div>
          <div className="mt-12 flex flex-wrap items-center gap-2 text-xs">
            {STAGES.map((s, i) => (
              <span key={s} className="flex items-center gap-2">
                <span className={`rounded-md px-2.5 py-1.5 font-medium ring-1 ring-inset ${s === "Outcome" ? "bg-ink-900 text-white ring-ink-900" : "bg-white text-slate-700 ring-slate-300"}`}>{s}</span>
                {i < STAGES.length - 1 && <span className="text-slate-300">→</span>}
              </span>
            ))}
          </div>
        </div>
      </section>

      <section id="gap" className="mx-auto max-w-6xl px-5 py-16">
        <h2 className="text-2xl font-semibold tracking-tight">Task automation stops at the task boundary.</h2>
        <p className="mt-2 max-w-2xl text-slate-600">Every hand-off between a script and a person is where work stalls: missing context, unclear ownership, exceptions that nobody planned for.</p>
        <div className="mt-8 grid gap-4 md:grid-cols-2">
          <div className="rounded-lg border border-slate-200 p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-slate-500">Traditional automation</div>
            <div className="mt-4 flex flex-wrap items-center gap-1.5 text-xs">
              {["Task", "Automation", "Task", "Human", "Task", "Human"].map((s, i) => (
                <span key={i} className="flex items-center gap-1.5"><span className={`rounded px-2 py-1 ${s === "Human" ? "bg-amber-100 text-amber-900" : "bg-slate-100 text-slate-700"}`}>{s}</span>{i < 5 && <span className="text-slate-300">→</span>}</span>
              ))}
            </div>
            <ul className="mt-4 space-y-1.5 text-sm text-slate-600"><li>• Automates isolated steps; people glue the rest together</li><li>• Exceptions halt the flow and land in someone’s inbox</li><li>• No owner for the end-to-end outcome</li></ul>
          </div>
          <div className="rounded-lg border-2 border-accent-500 bg-accent-50/40 p-5">
            <div className="text-xs font-semibold uppercase tracking-wide text-accent-700">FlowForge</div>
            <div className="mt-4 flex flex-wrap items-center gap-1.5 text-xs">
              {["Input", "Intelligence", "Execution", "Exception handling", "Outcome"].map((s, i) => (
                <span key={s} className="flex items-center gap-1.5"><span className="rounded bg-accent-600 px-2 py-1 font-medium text-white">{s}</span>{i < 4 && <span className="text-accent-500">→</span>}</span>
              ))}
            </div>
            <ul className="mt-4 space-y-1.5 text-sm text-slate-700"><li>• Owns the whole function, first input to finished outcome</li><li>• Detects, classifies, retries and resolves exceptions itself</li><li>• Asks a human only for judgment, approval or accountability</li></ul>
          </div>
        </div>
      </section>

      <section id="example" className="border-y border-slate-200 bg-slate-50">
        <div className="mx-auto grid max-w-6xl gap-8 px-5 py-16 lg:grid-cols-[360px_1fr]">
          <div>
            <div className="text-xs font-semibold uppercase tracking-wide text-accent-600">Procurement · live in the product</div>
            <h2 className="mt-2 text-2xl font-semibold tracking-tight">One sentence in. A verified purchase order out.</h2>
            <blockquote className="mt-5 rounded-md border-l-4 border-accent-500 bg-white p-4 text-[15px] leading-relaxed text-slate-800 shadow-sm">“I need a laptop for a new employee joining next Monday. Budget is ₹1,00,000.”</blockquote>
            <p className="mt-4 text-sm text-slate-600">Every step below runs through the same workflow engine you can inspect in the product — states, decisions, exceptions and a full audit trail.</p>
          </div>
          <ol className="space-y-2">
            {EXAMPLE.map(([name, text, kind], i) => (
              <li key={name} className="flex gap-3 rounded-md border border-slate-200 bg-white p-3">
                <span className={`mt-0.5 grid size-6 shrink-0 place-items-center rounded-full text-[11px] font-bold text-white ${kind === "exception" ? "bg-amber-500" : kind === "human" ? "bg-forge-500" : "bg-emerald-500"}`}>{i + 1}</span>
                <div><div className="text-sm font-semibold">{name}{kind === "human" && <span className="ml-2 rounded bg-orange-50 px-1.5 py-0.5 text-[10px] font-semibold text-orange-700">HUMAN JUDGMENT</span>}{kind === "exception" && <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-[10px] font-semibold text-amber-700">EXCEPTION</span>}</div><div className="text-sm text-slate-600">{text}</div></div>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section id="control" className="mx-auto max-w-6xl px-5 py-16">
        <h2 className="text-2xl font-semibold tracking-tight">Human-in-the-loop, by design.</h2>
        <p className="mt-2 max-w-2xl text-slate-600">Decision rules are configuration, not code. Administrators set the thresholds; FlowForge applies them and records the reasoning.</p>
        <div className="mt-8 grid gap-4 md:grid-cols-3">
          {LEVELS.map(([lvl, name, text, color]) => (
            <div key={lvl} className="rounded-lg border border-slate-200 p-5">
              <div className="flex items-center gap-2"><span className={`size-2.5 rounded-full ${color}`} /><span className="text-xs font-semibold uppercase tracking-wide text-slate-500">{lvl}</span></div>
              <div className="mt-2 text-lg font-semibold">{name}</div>
              <p className="mt-2 text-sm leading-relaxed text-slate-600">{text}</p>
            </div>
          ))}
        </div>
        <p className="mt-6 text-center text-sm font-medium text-slate-900">AI handles execution. Humans handle judgment.</p>
      </section>

      <section id="benefits" className="border-t border-slate-200 bg-slate-50">
        <div className="mx-auto grid max-w-6xl gap-4 px-5 py-16 sm:grid-cols-2 lg:grid-cols-4">
          {[["Outcome ownership", "From request to verified delivery — not a chain of disconnected tasks."], ["Exceptions that recover", "Classify, retry, find alternatives, escalate. Workflows resume; they don’t die."], ["Controlled autonomy", "Three levels of execution, configurable policies and permission-bounded tools."], ["Audit by default", "Who did what, why, and what a human decided — for every action."]].map(([t, d]) => (
            <div key={t} className="rounded-lg border border-slate-200 bg-white p-5"><div className="text-sm font-semibold">{t}</div><p className="mt-1.5 text-sm text-slate-600">{d}</p></div>
          ))}
        </div>
      </section>

      <section className="bg-ink-900 text-white">
        <div className="mx-auto flex max-w-6xl flex-col items-start justify-between gap-6 px-5 py-14 md:flex-row md:items-center">
          <div><h2 className="text-2xl font-semibold tracking-tight">See a function run itself in under three minutes.</h2><p className="mt-2 text-sm text-slate-400">Submit a request, watch the workflow execute, make the one human decision, read the audit trail.</p></div>
          <Link href="/login" className="rounded-md bg-white px-5 py-3 text-sm font-semibold text-ink-900 hover:bg-slate-100">Open the product →</Link>
        </div>
        <div className="border-t border-white/10 py-5 text-center text-xs text-slate-500">FlowForge · Automate the function. Not just the task. · Humans handle judgment. FlowForge handles the operational work.</div>
      </section>
    </div>
  );
}
