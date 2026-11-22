"use client";
import { cn } from "@/components/ui";
import { duration, fmtTime } from "@/lib/format";

const ICON = {
  pending: ["border-2 border-slate-300 bg-white text-slate-300", "○"],
  running: ["bg-accent-500 text-white ff-running", "◌"],
  completed: ["bg-emerald-500 text-white", "✓"],
  failed: ["bg-red-500 text-white", "✕"],
  waiting_human: ["bg-forge-500 text-white ff-waiting", "!"],
  resolved: ["bg-violet-500 text-white", "↻"],
  skipped: ["border-2 border-dashed border-slate-300 bg-slate-50 text-slate-400", "–"],
};
const RING = {
  running: "border-accent-500 bg-accent-50/50", waiting_human: "border-forge-500 bg-orange-50/60", failed: "border-red-300 bg-red-50/50",
};

function StatusIcon({ status }) {
  const [cls, glyph] = ICON[status] || ICON.pending;
  return (
    <span className={cn("relative z-10 grid size-7 shrink-0 place-items-center rounded-full text-xs font-bold", cls)}>
      {status === "running" ? <span className="size-3.5 animate-spin rounded-full border-2 border-white border-t-transparent" /> : glyph}
    </span>
  );
}

export default function WorkflowGraph({ steps, exceptions = [], approvals = [], selectedId, onSelect }) {
  return (
    <ol className="relative" aria-label="Workflow steps">
      {steps.map((s, i) => {
        const last = i === steps.length - 1;
        const done = ["completed", "resolved", "skipped"].includes(s.status);
        const next = steps[i + 1];
        const flowing = done && next && next.status === "running";
        const excs = exceptions.filter((e) => e.step_id === s.id);
        const isApproval = s.key === "approval";
        const humanApprovals = approvals.filter((a) => a.step_id === s.id && a.kind === "approval");
        const humanState = humanApprovals.at(-1);
        const humanActive = humanApprovals.some((a) => a.status === "pending");
        return (
          <li key={s.id} className="relative flex gap-3 ff-enter" style={{ animationDelay: `${i * 25}ms` }}>
            <div className="flex w-7 flex-col items-center">
              <StatusIcon status={s.status} />
              {!last && <span className={cn("-my-0.5 w-0.5 flex-1", flowing ? "ff-flowing" : done ? "bg-emerald-300" : "bg-slate-200")} style={{ minHeight: 14 }} />}
            </div>
            <div className="mb-2 flex min-w-0 flex-1 items-start gap-2">
              <button onClick={() => onSelect(s.id)} aria-pressed={selectedId === s.id}
                className={cn("min-w-0 flex-1 rounded-md border px-3 py-2 text-left transition-colors hover:border-slate-400",
                  selectedId === s.id ? "border-accent-500 bg-accent-50/60 ring-2 ring-accent-100" : RING[s.status] || "border-slate-200 bg-white")}>
                <div className="flex items-center justify-between gap-2">
                  <span className={cn("text-sm font-semibold", s.status === "pending" ? "text-slate-400" : "text-slate-900")}>{s.name}</span>
                  <span className="tnum shrink-0 text-[11px] text-slate-400">{s.completed_at ? duration(s.duration_ms) : s.started_at ? fmtTime(s.started_at) : ""}</span>
                </div>
                {(s.decision || s.error) && s.status !== "pending" && <div className="mt-0.5 truncate text-xs text-slate-500">{s.status === "waiting_human" || s.status === "failed" ? s.error || s.decision : s.decision}</div>}
                {excs.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {excs.map((e) => (
                      <span key={e.id} className={cn("rounded px-1.5 py-0.5 text-[10px] font-semibold", ["auto_resolved", "resolved_by_human"].includes(e.status) ? "bg-violet-100 text-violet-700" : e.status === "failed" ? "bg-red-100 text-red-700" : "bg-amber-100 text-amber-800")}>
                        ⚠ {e.code.replace(/_/g, " ").toLowerCase()} · {e.status.replace(/_/g, " ")}
                      </span>
                    ))}
                  </div>
                )}
              </button>
              {isApproval && (
                <div className="hidden items-center gap-1.5 sm:flex">
                  <span className={cn("h-0.5 w-5", humanState ? "bg-forge-500" : "bg-slate-200 [background-image:repeating-linear-gradient(90deg,#cbd5e1_0_4px,transparent_4px_8px)] bg-transparent")} />
                  <button onClick={() => onSelect(s.id)} className={cn("w-36 rounded-md border px-2.5 py-1.5 text-left text-[11px] leading-tight", humanActive ? "border-forge-500 bg-orange-50 ff-waiting" : humanState ? "border-emerald-300 bg-emerald-50" : "border-dashed border-slate-300 bg-slate-50 text-slate-400")}>
                    <div className="font-semibold">Human review</div>
                    <div className="truncate">{humanActive ? `Awaiting ${humanState.assigned_role}` : humanState ? `${humanState.status} · ${humanState.decided_by}` : "Only if rules require"}</div>
                  </button>
                </div>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}
