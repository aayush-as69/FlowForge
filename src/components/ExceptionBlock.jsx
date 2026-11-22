"use client";
import { Badge, StatusBadge } from "@/components/ui";
import { fmtTime } from "@/lib/format";

export default function ExceptionBlock({ e }) {
  return (
    <div className="rounded-md border border-slate-200 p-3">
      <div className="flex flex-wrap items-center gap-1.5"><span className="font-mono text-xs font-semibold text-slate-800">{e.code}</span><StatusBadge status={e.status} /><Badge>{e.category}</Badge><Badge tone={e.recoverable ? "green" : "red"}>{e.recoverable ? "recoverable" : "not recoverable"}</Badge><span className="text-[11px] text-slate-500">{e.attempts} attempt(s) · detected {fmtTime(e.detected_at)}</span></div>
      <p className="mt-1.5 text-sm text-slate-800">{e.message}</p>
      {e.resolution && <p className="mt-1 text-sm text-slate-600"><b>Resolution:</b> {e.resolution}{e.resolved_by && <span className="text-xs"> — {e.resolved_by}</span>}</p>}
      {e.resolution_trace?.length > 0 && (
        <ol className="mt-2 space-y-1 border-l-2 border-slate-200 pl-3">
          {e.resolution_trace.map((t, i) => <li key={i} className="text-xs text-slate-600"><span className={t.ok ? "text-emerald-600" : "text-red-600"}>{t.ok ? "✓" : "✕"}</span> <span className="font-mono text-[11px] text-slate-500">{t.action}</span> — {t.message}</li>)}
        </ol>
      )}
    </div>
  );
}

