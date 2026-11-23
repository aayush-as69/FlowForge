"use client";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import AuthProvider, { useAuth } from "@/components/AuthProvider";
import { Button, ErrorState, Spinner, cn, Dot } from "@/components/ui";
import { useApi } from "@/lib/hooks";

const NAV = [
  { href: "/dashboard", label: "Dashboard", icon: "▦" },
  { href: "/action-center", label: "Action Center", icon: "⚑", badge: "action" },
  { href: "/functions", label: "Functions", icon: "◈" },
  { href: "/workflows", label: "Workflows", icon: "⇢" },
  { href: "/approvals", label: "Approval Center", icon: "✓", perm: "approvals:read", badge: "pending_review" },
  { href: "/exceptions", label: "Exceptions", icon: "!", perm: "exceptions:read", badge: "open_exceptions" },
  { href: "/vendors", label: "Vendors", icon: "▤" },
  { href: "/integrations", label: "Integrations", icon: "⬡" },
  { href: "/policies", label: "Policies", icon: "§" },
  { href: "/audit", label: "Audit Trail", icon: "≡", perm: "audit:read" },
];

function Shell({ children }) {
  const { user, loading, error, can, logout } = useAuth();
  const pathname = usePathname();
  const [open, setOpen] = useState(false);
  const summary = useApi(user ? "/dashboard/summary" : null, { interval: 6000 });
  const m = summary.data?.metrics;

  if (loading) return <div className="grid min-h-screen place-items-center text-slate-500"><Spinner className="size-6" /></div>;
  if (error) return <div className="mx-auto max-w-lg pt-24"><ErrorState error={error} title="Could not load your session" onRetry={() => window.location.reload()} /></div>;
  if (!user) return null;

  const nav = (
    <nav className="flex-1 space-y-0.5 px-2 py-3" aria-label="Primary">
      {NAV.filter((n) => !n.perm || can(n.perm)).map((n) => {
        const active = pathname === n.href || pathname.startsWith(n.href + "/");
        const count = n.badge && m ? (n.badge === "action" ? (m.pending_review || 0) + (m.open_exceptions || 0) : m[n.badge]) : 0;
        return (
          <Link key={n.href} href={n.href} onClick={() => setOpen(false)}
            className={cn("flex items-center gap-2.5 rounded-md px-2.5 py-2 text-sm transition-colors",
              active ? "bg-white/10 font-medium text-white" : "text-slate-400 hover:bg-white/5 hover:text-slate-100")}>
            <span className="w-4 text-center font-mono text-xs opacity-80">{n.icon}</span>
            <span className="flex-1">{n.label}</span>
            {count > 0 && <span className={cn("tnum rounded px-1.5 text-[11px] font-semibold", n.badge === "pending_review" ? "bg-forge-500 text-white" : "bg-red-500/90 text-white")}>{count}</span>}
          </Link>
        );
      })}
    </nav>
  );

  return (
    <div className="min-h-screen lg:grid lg:grid-cols-[232px_1fr]">
      <aside className={cn("fixed inset-y-0 left-0 z-40 flex w-[232px] flex-col bg-ink-900 transition-transform lg:static lg:translate-x-0", open ? "translate-x-0" : "-translate-x-full")}>
        <Link href="/" className="flex items-center gap-2 px-4 py-4">
          <span className="grid size-7 place-items-center rounded-md bg-gradient-to-br from-accent-500 to-forge-500 text-sm font-bold text-white">F</span>
          <span className="text-[15px] font-semibold tracking-tight text-white">FlowForge</span>
        </Link>
        {nav}
        <div className="border-t border-white/10 p-3">
          <div className="flex items-center gap-2 px-1 text-xs text-slate-400"><Dot tone="green" pulse /> All systems operational</div>
        </div>
      </aside>
      {open && <div className="fixed inset-0 z-30 bg-black/40 lg:hidden" onClick={() => setOpen(false)} />}
      <div className="min-w-0">
        <header className="sticky top-0 z-20 flex h-12 items-center justify-between gap-3 border-b border-slate-200 bg-white/90 px-4 backdrop-blur">
          <div className="flex items-center gap-3">
            <button className="rounded p-1 text-slate-600 hover:bg-slate-100 lg:hidden" aria-label="Open navigation" onClick={() => setOpen(true)}>☰</button>
            <span className="hidden text-xs text-slate-500 sm:inline">Meridian Industries · <span className="font-medium text-slate-700">Procurement</span> function</span>
          </div>
          <div className="flex items-center gap-3">
            <div className="text-right leading-tight">
              <div className="text-xs font-medium text-slate-900">{user.name}</div>
              <div className="text-[11px] capitalize text-slate-500">{user.role}</div>
            </div>
            <Button size="sm" variant="secondary" onClick={logout}>Sign out</Button>
          </div>
        </header>
        <main className="mx-auto max-w-[1280px] px-4 py-6 sm:px-6">{children}</main>
      </div>
    </div>
  );
}

export default function AppLayout({ children }) {
  return <AuthProvider><Shell>{children}</Shell></AuthProvider>;
}
