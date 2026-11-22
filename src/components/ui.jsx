"use client";
import Link from "next/link";

export const cn = (...c) => c.filter(Boolean).join(" ");

const TONES = {
  slate: "bg-slate-100 text-slate-700 ring-slate-200",
  blue: "bg-accent-50 text-accent-700 ring-accent-100",
  green: "bg-emerald-50 text-emerald-700 ring-emerald-200",
  amber: "bg-amber-50 text-amber-800 ring-amber-200",
  red: "bg-red-50 text-red-700 ring-red-200",
  violet: "bg-violet-50 text-violet-700 ring-violet-200",
  orange: "bg-orange-50 text-orange-700 ring-orange-200",
};

export function Badge({ tone = "slate", children, className }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-medium ring-1 ring-inset", TONES[tone], className)}>
      {children}
    </span>
  );
}

const STATUS = {
  pending: ["slate", "Pending"], running: ["blue", "Running"], completed: ["green", "Completed"], failed: ["red", "Failed"],
  waiting_human: ["amber", "Waiting for human"], resolved: ["violet", "Resolved"], skipped: ["slate", "Skipped"],
  cancelled: ["slate", "Cancelled"], auto_resolved: ["green", "Auto-resolved"], awaiting_review: ["amber", "Awaiting review"],
  escalated: ["orange", "Escalated"], resolved_by_human: ["violet", "Resolved by human"], rejected: ["slate", "Rejected"],
  retrying: ["blue", "Retrying"], resolving: ["blue", "Recovering"], open: ["amber", "Open"], approved: ["green", "Approved"],
  modified: ["violet", "Modified"], connected: ["green", "Connected"], disconnected: ["red", "Disconnected"], degraded: ["amber", "Degraded"],
};

export function StatusBadge({ status }) {
  const [tone, label] = STATUS[status] || ["slate", status];
  return <Badge tone={tone}>{label}</Badge>;
}

export function Dot({ tone = "green", pulse }) {
  const c = { green: "bg-emerald-500", red: "bg-red-500", amber: "bg-amber-500", slate: "bg-slate-400", blue: "bg-accent-500" }[tone];
  return <span className={cn("inline-block size-2 rounded-full", c, pulse && "animate-pulse")} />;
}

export function Button({ variant = "secondary", size = "md", className, href, loading, children, ...props }) {
  const base = "inline-flex items-center justify-center gap-1.5 rounded-md font-medium transition-colors disabled:opacity-50 disabled:pointer-events-none whitespace-nowrap";
  const sizes = { sm: "h-7 px-2.5 text-xs", md: "h-9 px-3.5 text-sm", lg: "h-11 px-5 text-sm" };
  const variants = {
    primary: "bg-accent-600 text-white hover:bg-accent-700 shadow-sm",
    secondary: "bg-white text-slate-800 ring-1 ring-inset ring-slate-300 hover:bg-slate-50",
    danger: "bg-white text-red-700 ring-1 ring-inset ring-red-200 hover:bg-red-50",
    success: "bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm",
    dark: "bg-ink-900 text-white hover:bg-ink-800",
    ghost: "text-slate-600 hover:bg-slate-100",
  };
  const cls = cn(base, sizes[size], variants[variant], className);
  if (href) return <Link href={href} className={cls}>{children}</Link>;
  return (
    <button className={cls} disabled={loading || props.disabled} {...props}>
      {loading && <Spinner className="size-3.5" />}
      {children}
    </button>
  );
}

export function Spinner({ className }) {
  return <span className={cn("inline-block size-4 animate-spin rounded-full border-2 border-current border-t-transparent", className)} role="status" aria-label="Loading" />;
}

export function Card({ className, children, ...rest }) {
  return <section className={cn("rounded-lg border border-slate-200 bg-white shadow-[0_1px_2px_rgba(15,23,42,.04)]", className)} {...rest}>{children}</section>;
}

export function CardHeader({ title, subtitle, action, className }) {
  return (
    <div className={cn("flex items-start justify-between gap-3 border-b border-slate-100 px-4 py-3", className)}>
      <div>
        <h2 className="text-sm font-semibold text-slate-900">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-slate-500">{subtitle}</p>}
      </div>
      {action}
    </div>
  );
}

export function PageHeader({ title, subtitle, actions, eyebrow }) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div>
        {eyebrow && <div className="mb-1 text-[11px] font-semibold uppercase tracking-wider text-accent-600">{eyebrow}</div>}
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">{title}</h1>
        {subtitle && <p className="mt-1 max-w-3xl text-sm text-slate-500">{subtitle}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  );
}

export function Stat({ label, value, hint, tone = "slate", href }) {
  const tones = { slate: "text-slate-900", amber: "text-amber-700", red: "text-red-700", green: "text-emerald-700", blue: "text-accent-700" };
  const body = (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3 shadow-[0_1px_2px_rgba(15,23,42,.04)] transition-colors hover:border-slate-300">
      <div className="text-[11px] font-medium uppercase tracking-wide text-slate-500">{label}</div>
      <div className={cn("tnum mt-1 text-2xl font-semibold tracking-tight", tones[tone])}>{value}</div>
      {hint && <div className="mt-0.5 text-xs text-slate-500">{hint}</div>}
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

export function Skeleton({ className }) {
  return <div className={cn("ff-skeleton rounded", className)} aria-hidden />;
}

export function LoadingBlock({ rows = 4 }) {
  return (
    <div className="space-y-2 p-4" aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => <Skeleton key={i} className="h-9 w-full" />)}
    </div>
  );
}

export function ErrorState({ error, onRetry, title = "Something went wrong" }) {
  return (
    <div role="alert" className="m-4 rounded-md border border-red-200 bg-red-50 p-4 text-sm">
      <div className="font-medium text-red-800">{title}</div>
      <p className="mt-1 text-red-700">{error?.message || "Unexpected error."}</p>
      <p className="mt-1 text-xs text-red-600/80">{error?.status === 403 ? "Your role does not have access to this area." : "Nothing was lost — you can retry safely."}</p>
      {onRetry && error?.status !== 403 && <Button size="sm" className="mt-3" onClick={onRetry}>Retry</Button>}
    </div>
  );
}

export function EmptyState({ title, hint, action }) {
  return (
    <div className="flex flex-col items-center justify-center px-6 py-10 text-center">
      <div className="mb-3 grid size-9 place-items-center rounded-full bg-slate-100 text-slate-400">○</div>
      <div className="text-sm font-medium text-slate-800">{title}</div>
      {hint && <p className="mt-1 max-w-sm text-xs text-slate-500">{hint}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  );
}

/** Renders loading / error / empty / content for an useApi() result. */
export function Async({ state, empty, skeletonRows, children }) {
  if (state.loading && !state.data) return <LoadingBlock rows={skeletonRows} />;
  if (state.error && !state.data) return <ErrorState error={state.error} onRetry={state.reload} />;
  if (empty && empty(state.data)) return empty.element;
  return children(state.data);
}

export function Tabs({ tabs, value, onChange }) {
  return (
    <div className="flex gap-1 overflow-x-auto border-b border-slate-200" role="tablist">
      {tabs.map((t) => (
        <button key={t.key} role="tab" aria-selected={value === t.key} onClick={() => onChange(t.key)}
          className={cn("-mb-px flex items-center gap-1.5 whitespace-nowrap border-b-2 px-3 py-2 text-sm font-medium transition-colors",
            value === t.key ? "border-accent-600 text-accent-700" : "border-transparent text-slate-500 hover:text-slate-800")}>
          {t.label}
          {t.count !== undefined && <span className="tnum rounded bg-slate-100 px-1.5 text-[11px] text-slate-600">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Kv({ label, children, mono }) {
  return (
    <div className="grid grid-cols-[120px_1fr] gap-2 py-1.5 text-sm">
      <dt className="text-slate-500">{label}</dt>
      <dd className={cn("min-w-0 break-words text-slate-900", mono && "font-mono text-xs")}>{children ?? "—"}</dd>
    </div>
  );
}

export function Json({ value, className }) {
  if (value === null || value === undefined) return <span className="text-xs text-slate-400">—</span>;
  return (
    <pre className={cn("max-h-64 overflow-auto rounded-md bg-slate-50 p-2.5 font-mono text-[11px] leading-relaxed text-slate-700 ring-1 ring-inset ring-slate-200", className)}>
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

export function Pager({ page, pages, total, onPage }) {
  if (!total) return null;
  return (
    <div className="flex items-center justify-between border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
      <span className="tnum">{total} total</span>
      <div className="flex items-center gap-2">
        <Button size="sm" variant="secondary" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <span className="tnum">Page {page} of {pages}</span>
        <Button size="sm" variant="secondary" disabled={page >= pages} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  );
}

export const inputCls = "h-9 w-full rounded-md border border-slate-300 bg-white px-2.5 text-sm text-slate-900 placeholder:text-slate-400 focus:border-accent-500 focus:outline-none focus:ring-2 focus:ring-accent-100";

export function Field({ label, hint, error, children }) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium text-slate-700">{label}</span>
      {children}
      {hint && !error && <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>}
      {error && <span className="mt-1 block text-[11px] text-red-600">{error}</span>}
    </label>
  );
}
