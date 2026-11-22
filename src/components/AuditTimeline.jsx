"use client";
import { useState } from "react";
import { Badge, Json, cn } from "@/components/ui";
import { fmtTime, fmtDateTime, titleCase } from "@/lib/format";

const ACTOR = { ai: ["blue", "AI"], system: ["slate", "System"], user: ["orange", "Human"], tool: ["violet", "Tool"] };
const RESULT_TONE = { ok: "green", pass: "green", approved: "green", exception: "amber", failed: "red", error: "red", blocked: "red", denied: "red", rejected: "slate", fail: "red" };

export function humanAction(a) {
  return titleCase(a.replace(/[._]/g, " "));
}

export function AuditRow({ e, showWorkflow, showDate }) {
  const [open, setOpen] = useState(false);
  const [tone, label] = ACTOR[e.actor_type] || ACTOR.system;
  return (
    <li className="px-4 py-2.5">
      <button onClick={() => setOpen(!open)} className="flex w-full items-start gap-3 text-left" aria-expanded={open}>
        <span className="tnum w-[84px] shrink-0 pt-0.5 font-mono text-xs text-slate-500">{showDate ? fmtDateTime(e.ts) : fmtTime(e.ts)}</span>
        <Badge tone={tone} className="mt-0.5 w-[52px] shrink-0 justify-center">{label}</Badge>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-2 gap-y-0.5">
            <span className="text-sm font-medium text-slate-900">{humanAction(e.action)}</span>
            <span className="text-xs text-slate-500">{e.actor}</span>
            {showWorkflow && e.workflow_ref && <Badge>{e.workflow_ref}</Badge>}
            {e.result && e.result !== "recorded" && <Badge tone={RESULT_TONE[e.result] || "slate"}>{e.result}</Badge>}
            {e.duration_ms !== null && e.duration_ms !== undefined && <span className="tnum text-[11px] text-slate-400">{e.duration_ms} ms</span>}
          </div>
          {e.reason && <div className={cn("mt-0.5 text-xs text-slate-600", !open && "line-clamp-2")}>{e.reason}</div>}
        </div>
      </button>
      {open && (
        <div className="ml-[148px] mt-2 grid gap-2 md:grid-cols-2">
          <div><div className="mb-1 text-[11px] font-semibold uppercase text-slate-500">Input</div><Json value={e.input} /></div>
          <div><div className="mb-1 text-[11px] font-semibold uppercase text-slate-500">Output</div><Json value={e.output} /></div>
          <div className="text-[11px] text-slate-500 md:col-span-2">Status: <b>{e.status}</b> · Event #{e.id}</div>
        </div>
      )}
    </li>
  );
}

export default function AuditTimeline({ events }) {
  return <ul className="divide-y divide-slate-100">{events.map((e) => <AuditRow key={e.id} e={e} />)}</ul>;
}
