"use client";

import { SiteGantt } from "@/lib/types";
import { useState } from "react";

interface Props {
  sites: SiteGantt[];
  onSelectSite: (siteId: string) => void;
}

function statusBadge(status: string) {
  const map: Record<string, string> = {
    COMPLETED: "bg-emerald-100 text-emerald-800 border-emerald-300",
    "IN PROGRESS": "bg-blue-100 text-blue-800 border-blue-300",
    PENDING: "bg-gray-100 text-gray-700 border-gray-300",
    DELAYED: "bg-amber-100 text-amber-800 border-amber-300",
    "HIGH RISK": "bg-orange-100 text-orange-800 border-orange-300",
    CRITICAL: "bg-red-100 text-red-800 border-red-300",
    "EXCLUDED - CREW SHORTAGE": "bg-orange-100 text-orange-800 border-orange-300",
    "EXCLUDED - PACE CONSTRAINT": "bg-purple-100 text-purple-800 border-purple-300",
  };
  const cls = map[status] || "bg-gray-100 text-gray-700 border-gray-300";
  return (
    <span className={`px-2 py-0.5 text-xs font-semibold rounded-full border ${cls}`}>
      {status}
    </span>
  );
}

export default function SiteTable({ sites, onSelectSite }: Props) {
  const [search, setSearch] = useState("");
  const [sortCol, setSortCol] = useState<string>("site_id");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");

  const filtered = sites.filter(
    (s) =>
      s.site_id.toLowerCase().includes(search.toLowerCase()) ||
      s.project_name.toLowerCase().includes(search.toLowerCase()) ||
      s.market.toLowerCase().includes(search.toLowerCase())
  );

  const sorted = [...filtered].sort((a, b) => {
    const va = (a as unknown as Record<string, unknown>)[sortCol];
    const vb = (b as unknown as Record<string, unknown>)[sortCol];
    const cmp = String(va ?? "").localeCompare(String(vb ?? ""), undefined, { numeric: true });
    return sortDir === "asc" ? cmp : -cmp;
  });

  function toggleSort(col: string) {
    if (sortCol === col) setSortDir(sortDir === "asc" ? "desc" : "asc");
    else { setSortCol(col); setSortDir("asc"); }
  }

  const colHdr = (col: string, label: string) => (
    <th
      className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase cursor-pointer hover:text-gray-700 select-none"
      onClick={() => toggleSort(col)}
    >
      {label} {sortCol === col ? (sortDir === "asc" ? "↑" : "↓") : ""}
    </th>
  );

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
      <div className="px-4 py-3 border-b border-gray-100 flex items-center gap-3">
        <input
          type="text"
          placeholder="Search sites..."
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm w-64 focus:outline-none focus:ring-2 focus:ring-blue-500"
        />
        <span className="text-sm text-gray-500">{sorted.length} sites</span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              {colHdr("site_id", "Site ID")}
              {colHdr("project_name", "Project")}
              {colHdr("market", "Market")}
              {colHdr("vendor_name", "Vendor")}
              {colHdr("overall_status", "Status")}
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Milestones</th>
              {colHdr("forecasted_cx_start_date", "Forecast Cx Start")}
            </tr>
          </thead>
          <tbody>
            {sorted.map((s) => (
              <tr
                key={s.site_id}
                onClick={() => onSelectSite(s.site_id)}
                className="border-b border-gray-50 hover:bg-blue-50 cursor-pointer transition-colors"
              >
                <td className="px-3 py-2 font-mono text-blue-700 font-medium">{s.site_id}</td>
                <td className="px-3 py-2 text-gray-700">{s.project_name}</td>
                <td className="px-3 py-2 text-gray-600">{s.market}</td>
                <td className="px-3 py-2 text-gray-600">{s.vendor_name || "—"}</td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-1.5">
                    {statusBadge(s.overall_status)}
                    {s.milestone_range && (
                      <span className="text-[10px] font-semibold text-gray-500">({s.milestone_range})</span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2">
                  <div className="flex items-center gap-2 text-xs">
                    <span className="text-emerald-600">{s.milestone_status_summary.on_track} on track</span>
                    <span className="text-blue-500">{s.milestone_status_summary.in_progress} in progress</span>
                    {s.milestone_status_summary.delayed > 0 && (
                      <span className="text-red-500">{s.milestone_status_summary.delayed} delayed</span>
                    )}
                  </div>
                </td>
                <td className="px-3 py-2 text-gray-600">{s.forecasted_cx_start_date || "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
