"use client";
import { Badge, Json, cn } from "@/components/ui";
import { inr, titleCase } from "@/lib/format";

export function PolicyList({ results }) {
  if (!results?.length) return null;
  const icon = { pass: ["✓", "text-emerald-600"], warn: ["⚠", "text-amber-600"], fail: ["✕", "text-red-600"] };
  return (
    <ul className="space-y-1">
      {results.map((r) => (
        <li key={r.key + r.message} className="flex gap-2 text-sm">
          <span className={cn("w-4 shrink-0 text-center font-semibold", icon[r.status][1])}>{icon[r.status][0]}</span>
          <span className="text-slate-800">{r.message}{r.approval_role && <Badge tone="amber" className="ml-1.5">{r.approval_role} approval</Badge>}</span>
        </li>
      ))}
    </ul>
  );
}

export function VendorTable({ offers, selectedId, compact }) {
  if (!offers?.length) return null;
  return (
    <div className="overflow-x-auto rounded-md ring-1 ring-inset ring-slate-200">
      <table className="w-full min-w-[640px] text-left text-xs">
        <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500">
          <tr>{["Vendor", "Unit price", "Delivery", "Rating", "Warranty", "Reliability", "vs history", "Score", ""].map((h) => <th key={h} className="px-2.5 py-2 font-medium">{h}</th>)}</tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {offers.map((o) => {
            const sel = o.vendor_id === selectedId;
            const anomaly = o.price_delta_pct !== null && o.price_delta_pct > 15;
            return (
              <tr key={o.vendor_id} className={cn(sel && "bg-accent-50/60", !o.eligible && "text-slate-400")}>
                <td className="px-2.5 py-2 font-medium text-slate-900">{o.name}{!o.approved && <Badge tone="red" className="ml-1">unapproved</Badge>}</td>
                <td className="tnum px-2.5 py-2">{inr(o.unit_price)}</td>
                <td className="tnum px-2.5 py-2">{o.delivery_days} d</td>
                <td className="tnum px-2.5 py-2">{o.rating}</td>
                <td className="tnum px-2.5 py-2">{o.warranty_years} yr</td>
                <td className="tnum px-2.5 py-2">{o.reliability}%</td>
                <td className={cn("tnum px-2.5 py-2", anomaly && "font-semibold text-amber-700")}>{o.price_delta_pct === null ? "—" : `${o.price_delta_pct > 0 ? "+" : ""}${o.price_delta_pct}%`}</td>
                <td className="tnum px-2.5 py-2">{o.eligible ? o.score.toFixed(3) : "—"}</td>
                <td className="px-2.5 py-2">
                  {sel ? <Badge tone="blue">Recommended</Badge> : o.eligible ? <Badge tone="green">#{o.rank}</Badge> : <span title={o.reasons.join("; ")} className="text-[11px] text-red-600">{compact ? "Excluded" : o.reasons[0]}</span>}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function DecisionView({ out }) {
  const tone = { 1: "green", 2: "amber", 3: "orange" }[out.level];
  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2"><Badge tone={tone}>Level {out.level} · {titleCase(out.outcome)}</Badge>{out.required_role && <Badge>needs {out.required_role}</Badge>}{out.approval_covered && <Badge tone="green">covered by existing approval</Badge>}</div>
      <ul className="space-y-1">
        {out.trace.map((t, i) => (
          <li key={i} className="flex gap-2 text-xs"><span className={cn("w-4 text-center font-bold", t.matched ? "text-amber-600" : "text-emerald-600")}>{t.matched ? "▲" : "✓"}</span><span className="text-slate-700"><span className="font-mono text-[11px] text-slate-500">{t.rule}</span> — {t.detail}</span></li>
        ))}
      </ul>
    </div>
  );
}

export function StepOutput({ step }) {
  const o = step.output;
  if (!o) return <span className="text-xs text-slate-400">No output yet</span>;
  if (step.key === "policy_check") return <PolicyList results={o.results} />;
  if (step.key === "vendor_evaluation" && o.offers) return <div className="space-y-2"><VendorTable offers={o.offers} selectedId={o.selected?.vendor_id} compact /><p className="text-sm text-slate-700">{o.recommendation}</p></div>;
  if (step.key === "decision" && o.trace) return <div className="space-y-3"><DecisionView out={o} />{o.policy && <PolicyList results={o.policy.results} />}</div>;
  if (step.key === "verification" && o.checks) return (
    <ul className="space-y-1">{o.checks.map((c) => <li key={c.check} className="flex gap-2 text-sm"><span className={cn("w-4 text-center font-semibold", c.ok ? "text-emerald-600" : "text-red-600")}>{c.ok ? "✓" : "✕"}</span><span>{c.check} <span className="text-xs text-slate-500">— {c.detail}</span></span></li>)}</ul>
  );
  if (step.key === "understand" && o.extracted) return (
    <dl className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm">
      {Object.entries(o.extracted).filter(([, v]) => v).map(([k, v]) => <div key={k}><dt className="text-[11px] uppercase text-slate-500">{titleCase(k)}</dt><dd>{k === "budget" ? inr(v) : String(v)}</dd></div>)}
    </dl>
  );
  return <Json value={o} />;
}
