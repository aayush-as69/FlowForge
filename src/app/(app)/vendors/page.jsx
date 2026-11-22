"use client";
import { useState } from "react";
import { api } from "@/lib/api";
import { useApi } from "@/lib/hooks";
import { useAuth } from "@/components/AuthProvider";
import { Async, Badge, Button, Card, PageHeader } from "@/components/ui";
import { inr } from "@/lib/format";

export default function Vendors() {
  const { can } = useAuth();
  const state = useApi("/vendors");
  const [error, setError] = useState(null);
  async function toggle(v, field) {
    setError(null);
    try { await api(`/vendors/${v.id}`, { method: "PATCH", body: { [field]: !v[field] } }); await state.reload(); } catch (e) { setError(e.message); }
  }
  return (
    <>
      <PageHeader title="Vendor database" subtitle="Approved vendors, catalog prices and historical performance used by vendor evaluation and the price-anomaly check." />
      {error && <div role="alert" className="mb-3 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">{error}</div>}
      <Card>
        <Async state={state} skeletonRows={5}>
          {(vendors) => (
            <div className="overflow-x-auto"><table className="w-full min-w-[900px] text-left text-sm">
              <thead className="bg-slate-50 text-[11px] uppercase tracking-wide text-slate-500"><tr>{["Vendor", "Status", "Laptop quote", "vs history", "Delivery", "Rating", "Warranty", "Reliability", "Compliance", "Categories", ""].map((h) => <th key={h} className="px-3 py-2 font-medium">{h}</th>)}</tr></thead>
              <tbody className="divide-y divide-slate-100">{vendors.map((v) => {
                const q = v.catalog.laptop, h = v.historical_avg.laptop;
                const delta = q && h ? Math.round(((q - h) / h) * 1000) / 10 : null;
                return (
                  <tr key={v.id}>
                    <td className="px-3 py-2.5 font-medium">{v.name}{v.notes && <div className="text-[11px] font-normal text-red-600">{v.notes}</div>}</td>
                    <td className="px-3 py-2.5"><div className="flex flex-col items-start gap-1"><Badge tone={v.approved ? "green" : "red"}>{v.approved ? "Approved" : "Unapproved"}</Badge><Badge tone={v.available ? "slate" : "amber"}>{v.available ? "Available" : "Unavailable"}</Badge></div></td>
                    <td className="tnum px-3 py-2.5">{inr(q)}</td><td className={`tnum px-3 py-2.5 ${delta > 15 ? "font-semibold text-amber-700" : ""}`}>{delta === null ? "—" : `${delta > 0 ? "+" : ""}${delta}%`}</td>
                    <td className="tnum px-3 py-2.5">{v.delivery_days} d</td><td className="tnum px-3 py-2.5">{v.rating}</td><td className="tnum px-3 py-2.5">{v.warranty_years} yr</td><td className="tnum px-3 py-2.5">{v.reliability_score}%</td><td className="tnum px-3 py-2.5">{v.compliance_score}%</td>
                    <td className="px-3 py-2.5 text-xs text-slate-500">{v.categories.join(", ")}</td>
                    <td className="px-3 py-2.5">{can("vendors:write") && <div className="flex gap-1"><Button size="sm" onClick={() => toggle(v, "approved")}>{v.approved ? "Revoke" : "Approve"}</Button><Button size="sm" variant="ghost" onClick={() => toggle(v, "available")}>{v.available ? "Mark out" : "Mark in"}</Button></div>}</td>
                  </tr>
                );
              })}</tbody></table></div>
          )}
        </Async>
      </Card>
    </>
  );
}
