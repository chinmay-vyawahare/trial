"use client";

import { useEffect, useState, useCallback } from "react";
import { getCxActualSummary } from "@/lib/api";
import type { CxActualSummaryResponse, CxActualDay, CxActualSite } from "@/lib/types";

interface Props {
  region: string[];
  market: string[];
  area: string[];
  siteId: string;
  vendor: string;
  userId: string;
  refreshKey: number;
}

export default function CxActualChart({
  region,
  market,
  area,
  siteId,
  vendor,
  userId,
  refreshKey,
}: Props) {
  const [data, setData] = useState<CxActualSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedDay, setExpandedDay] = useState<string | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getCxActualSummary({
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        region: region.length ? region : undefined,
        market: market.length ? market : undefined,
        area: area.length ? area : undefined,
        site_id: siteId || undefined,
        vendor: vendor || undefined,
        user_id: userId || undefined,
      });
      setData(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load CX actual data");
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, region, market, area, siteId, vendor, userId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const maxCount = data ? Math.max(...data.days.map((d) => d.total), 0) : 0;

  const COLORS = [
    "#10b981", "#22c55e", "#14b8a6", "#0ea5e9",
    "#3b82f6", "#6366f1", "#8b5cf6", "#a855f7",
  ];

  function barColor(idx: number) {
    return COLORS[idx % COLORS.length];
  }

  function formatDay(dateStr: string) {
    const d = new Date(dateStr + "T00:00:00");
    const days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
    return days[d.getDay()];
  }

  return (
    <div className="h-full overflow-auto p-5 space-y-5">
      {/* Date filter bar */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-3 flex items-center gap-4">
        <label className="text-xs font-semibold text-gray-600">Actual CX Date Range:</label>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="px-2 py-1 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-emerald-400"
          />
          <span className="text-xs text-gray-400">to</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="px-2 py-1 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-emerald-400"
          />
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="px-3 py-1 text-xs font-semibold rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "Loading..." : "Apply"}
        </button>
        {(startDate || endDate) && (
          <button
            onClick={() => { setStartDate(""); setEndDate(""); }}
            className="px-3 py-1 text-xs font-medium rounded-lg border border-gray-200 text-gray-500 hover:bg-gray-50 transition-colors"
          >
            Clear Dates
          </button>
        )}
        {data && (
          <span className="ml-auto text-[11px] text-gray-400">
            Showing: {data.start_date} to {data.end_date}
          </span>
        )}
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin w-8 h-8 border-3 border-emerald-500 border-t-transparent rounded-full" />
        </div>
      )}

      {!loading && error && (
        <div className="flex items-center justify-center py-20 text-red-500 text-sm">
          {error}
        </div>
      )}

      {!loading && !error && (!data || data.days.length === 0) && (
        <div className="flex items-center justify-center py-20 text-gray-400 text-sm">
          No actual construction data found for this date range.
        </div>
      )}

      {!loading && !error && data && data.days.length > 0 && <>
      {/* Summary cards */}
      <div className="flex items-center gap-4">
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-3 flex flex-col items-center">
          <span className="text-2xl font-bold text-emerald-600">{data.total_sites}</span>
          <span className="text-xs text-gray-500 mt-0.5">Total Sites</span>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-3 flex flex-col items-center">
          <span className="text-2xl font-bold text-teal-600">{data.total_days}</span>
          <span className="text-xs text-gray-500 mt-0.5">Days with Activity</span>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-3 flex flex-col items-center">
          <span className="text-2xl font-bold text-gray-700">{data.start_date}</span>
          <span className="text-xs text-gray-500 mt-0.5">From</span>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-3 flex flex-col items-center">
          <span className="text-2xl font-bold text-gray-700">{data.end_date}</span>
          <span className="text-xs text-gray-500 mt-0.5">To</span>
        </div>
      </div>

      {/* Day-wise bar chart */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">
          CX Actual — Daily Site Counts (Actual Construction Start)
        </h3>

        <div className="space-y-1.5">
          {data.days.map((d: CxActualDay, idx: number) => {
            const pct = maxCount > 0 ? (d.total / maxCount) * 100 : 0;
            const isExpanded = expandedDay === d.date;

            return (
              <div key={d.date}>
                <button
                  onClick={() => setExpandedDay(isExpanded ? null : d.date)}
                  className="w-full flex items-center gap-3 group cursor-pointer"
                >
                  <span className="text-[11px] font-medium text-gray-500 w-24 text-right shrink-0">
                    {d.date}
                  </span>
                  <span className="text-[10px] text-gray-400 w-10 shrink-0">
                    {formatDay(d.date)}
                  </span>
                  <div className="flex-1 h-7 bg-gray-100 rounded-lg overflow-hidden">
                    <div
                      className="h-full rounded-lg transition-all duration-300 flex items-center px-2"
                      style={{
                        width: `${Math.max(pct, 5)}%`,
                        background: barColor(idx),
                      }}
                    >
                      <span className="text-[11px] font-bold text-white drop-shadow-sm">
                        {d.total}
                      </span>
                    </div>
                  </div>
                  <span className="text-[10px] text-gray-400 w-4">
                    {isExpanded ? "▲" : "▼"}
                  </span>
                </button>

                {isExpanded && (
                  <div className="ml-[8.5rem] mt-2 mb-3 rounded-lg border border-gray-200 overflow-hidden">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-gray-50 text-gray-500">
                          <th className="px-3 py-1.5 text-left font-semibold">Site ID</th>
                          <th className="px-3 py-1.5 text-left font-semibold">Project</th>
                          <th className="px-3 py-1.5 text-left font-semibold">Region</th>
                          <th className="px-3 py-1.5 text-left font-semibold">Market</th>
                          <th className="px-3 py-1.5 text-left font-semibold">Area</th>
                          <th className="px-3 py-1.5 text-left font-semibold">Vendor</th>
                          <th className="px-3 py-1.5 text-left font-semibold">CX Actual Date</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.sites.map((s: CxActualSite) => (
                          <tr
                            key={`${s.site_id}-${s.project_id}`}
                            className="border-t border-gray-100 hover:bg-emerald-50/40"
                          >
                            <td className="px-3 py-1.5 font-medium text-gray-700">{s.site_id}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.project_name}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.region}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.market}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.area}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.vendor}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.cx_actual_date}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </div>
      </>}
    </div>
  );
}
