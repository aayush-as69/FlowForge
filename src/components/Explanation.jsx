"use client";
import { useApi } from "@/lib/hooks";
import { Async, Badge, Card, CardHeader, EmptyState } from "@/components/ui";

const MARK = { pass: ["✓", "text-emerald-600"], warn: ["!", "text-amber-600"], fail: ["✕", "text-red-600"], skipped: ["–", "text-slate-400"] };

export function Check({ ok, children }) {
  return (
    <li className="flex gap-2 text-sm">
      <span aria-hidden className={ok ? "text-emerald-600" : "text-red-600"}>{ok ? "✓" : "✕"}</span>
      <span className="sr-only">{ok ? "Satisfied:" : "Not satisfied:"}</span>
      <span className="text-slate-800">{children}</span>
    </li>
  );
}

function Section({ title, children }) {
  return <Card><CardHeader title={title} /><div className="space-y-2 p-4">{children}</div></Card>;
}

export function ExplanationView({ data }) {
  const { headline, extraction, policy, vendor, autonomy, human, exceptions } = data;
  return (
    <div className="space-y-3">
      <Card className="border-forge-200 bg-forge-50/40"><div className="p-4 text-sm font-medium text-slate-900">{headline}</div></Card>
      {extraction && (
        <Section title="1. Understanding the request">
          <p className="text-sm text-slate-700">
            Read by <b>{extraction.engine}</b> with {Math.round((extraction.confidence ?? 0) * 100)}% confidence
            {extraction.corrected ? ", then corrected by a person" : ""}.
          </p>
        </Section>
      )}
      {policy && (
        <Section title="2. Policy checks">
          <ul className="space-y-1.5">
            {policy.results.map((r) => {
              const [mark, tone] = MARK[r.status] || MARK.skipped;
              return (
                <li key={r.key} className="flex gap-2 text-sm">
                  <span aria-hidden className={tone}>{mark}</span>
                  <span className="text-slate-800"><b>{r.name}</b> — {r.label}{r.message ? `. ${r.message}` : ""}</span>
                </li>
              );
            })}
          </ul>
        </Section>
      )}
      {vendor && (
        <Section title={`3. Why ${vendor.selected}`}>
          <ul className="space-y-1.5">{vendor.reasons.map((r, i) => <Check key={i} ok={r.ok}>{r.text}</Check>)}</ul>
          {vendor.rejected.length > 0 && (
            <div className="pt-2">
              <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-slate-500">Not chosen</div>
              <ul className="space-y-1">
                {vendor.rejected.map((r) => (
                  <li key={r.vendor} className="text-sm text-slate-700"><b>{r.vendor}</b> — {r.why}{r.eligible ? "" : " "}{!r.eligible && <Badge tone="red">ineligible</Badge>}</li>
                ))}
              </ul>
            </div>
          )}
        </Section>
      )}
      {autonomy && (
        <Section title="4. How much autonomy was used">
          <p className="text-sm text-slate-800"><Badge tone={autonomy.level === 1 ? "green" : autonomy.level === 2 ? "amber" : "red"}>Level {autonomy.level}</Badge> {autonomy.plain}</p>
          <ul className="list-disc pl-5 text-sm text-slate-700">{autonomy.reasons.map((r, i) => <li key={i}>{r}</li>)}</ul>
        </Section>
      )}
      {(human.length > 0 || exceptions.length > 0) && (
        <Section title="5. People and exceptions">
          {human.map((h) => (
            <p key={h.approval_id} className="text-sm text-slate-800">
              <b>{h.title}</b> — {h.status === "pending" ? "waiting for a decision" : `${h.status} by ${h.by} (${h.role})`}{h.note ? `: “${h.note}”` : ""}
            </p>
          ))}
          {exceptions.map((e, i) => (
            <p key={i} className="text-sm text-slate-800"><b>{e.code}</b> — {e.message}{e.resolution ? ` → ${e.resolution}` : ""}</p>
          ))}
        </Section>
      )}
    </div>
  );
}

export default function Explanation({ workflowId }) {
  const state = useApi(`/workflows/${workflowId}/explanation`);
  return (
    <Async state={state} skeletonRows={5} empty={Object.assign((d) => !d, { element: <EmptyState title="Nothing to explain yet" /> })}>
      {(d) => <ExplanationView data={d} />}
    </Async>
  );
}
