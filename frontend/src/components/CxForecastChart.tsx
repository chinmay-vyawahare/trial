"use client";

import { useEffect, useState, useCallback } from "react";
import { getCxForecastSummary } from "@/lib/api";
import type { CxForecastSummaryResponse, CxForecastWeek, CxForecastSite } from "@/lib/types";

interface Props {
  region: string;
  market: string;
  area: string;
  siteId: string;
  vendor: string;
  userId: string;
  refreshKey: number;
}

export default function CxForecastChart({
  region,
  market,
  area,
  siteId,
  vendor,
  userId,
  refreshKey,
}: Props) {
  const [data, setData] = useState<CxForecastSummaryResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedWeek, setExpandedWeek] = useState<string | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await getCxForecastSummary({
        start_date: startDate || undefined,
        end_date: endDate || undefined,
        region: region || undefined,
        market: market || undefined,
        area: area || undefined,
        site_id: siteId || undefined,
        vendor: vendor || undefined,
        user_id: userId || undefined,
      });
      setData(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load CX forecast");
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, region, market, area, siteId, vendor, userId]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const maxCount = data ? Math.max(...data.weeks.map((w) => w.total), 0) : 0;

  function weekKey(w: CxForecastWeek) {
    return `${w.year}-W${w.week}`;
  }

  const COLORS = [
    "#3b82f6", "#6366f1", "#8b5cf6", "#a855f7",
    "#0ea5e9", "#14b8a6", "#10b981", "#22c55e",
  ];

  function barColor(idx: number) {
    return COLORS[idx % COLORS.length];
  }

  return (
    <div className="h-full overflow-auto p-5 space-y-5">
      {/* Date filter bar */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-3 flex items-center gap-4">
        <label className="text-xs font-semibold text-gray-600">CX Start Date Range:</label>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
            className="px-2 py-1 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <span className="text-xs text-gray-400">to</span>
          <input
            type="date"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
            className="px-2 py-1 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="px-3 py-1 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
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
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
        </div>
      )}

      {!loading && error && (
        <div className="flex items-center justify-center py-20 text-red-500 text-sm">
          {error}
        </div>
      )}

      {!loading && !error && (!data || data.weeks.length === 0) && (
        <div className="flex items-center justify-center py-20 text-gray-400 text-sm">
          No CX forecast data available.
        </div>
      )}

      {!loading && !error && data && data.weeks.length > 0 && <>
      {/* Summary cards */}
      <div className="flex items-center gap-4">
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-3 flex flex-col items-center">
          <span className="text-2xl font-bold text-blue-600">{data.total_sites}</span>
          <span className="text-xs text-gray-500 mt-0.5">Total Sites</span>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-3 flex flex-col items-center">
          <span className="text-2xl font-bold text-indigo-600">{data.total_weeks}</span>
          <span className="text-xs text-gray-500 mt-0.5">Weeks</span>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-3 flex flex-col items-center">
          <span className="text-2xl font-bold text-gray-700">
            {data.weeks.length > 0 ? data.weeks[0].week_start : "—"}
          </span>
          <span className="text-xs text-gray-500 mt-0.5">Earliest Week</span>
        </div>
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-5 py-3 flex flex-col items-center">
          <span className="text-2xl font-bold text-gray-700">
            {data.weeks.length > 0 ? data.weeks[data.weeks.length - 1].week_end : "—"}
          </span>
          <span className="text-xs text-gray-500 mt-0.5">Latest Week</span>
        </div>
      </div>

      {/* Bar chart */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
        <h3 className="text-sm font-semibold text-gray-700 mb-4">
          CX Forecast — Weekly Site Counts (Planned Construction Start)
        </h3>

        <div className="space-y-2">
          {data.weeks.map((w, idx) => {
            const key = weekKey(w);
            const pct = maxCount > 0 ? (w.total / maxCount) * 100 : 0;
            const isExpanded = expandedWeek === key;

            return (
              <div key={key}>
                {/* Bar row */}
                <button
                  onClick={() => setExpandedWeek(isExpanded ? null : key)}
                  className="w-full flex items-center gap-3 group cursor-pointer"
                >
                  <span className="text-[11px] font-medium text-gray-500 w-28 text-right shrink-0">
                    W{w.week} {w.year}
                  </span>
                  <span className="text-[10px] text-gray-400 w-36 shrink-0">
                    {w.week_start} — {w.week_end}
                  </span>
                  <div className="flex-1 h-7 bg-gray-100 rounded-lg overflow-hidden">
                    <div
                      className="h-full rounded-lg transition-all duration-300 flex items-center px-2"
                      style={{
                        width: `${Math.max(pct, 4)}%`,
                        background: barColor(idx),
                      }}
                    >
                      <span className="text-[11px] font-bold text-white drop-shadow-sm">
                        {w.total}
                      </span>
                    </div>
                  </div>
                  <span className="text-[10px] text-gray-400 w-4">
                    {isExpanded ? "▲" : "▼"}
                  </span>
                </button>

                {/* Drilldown table */}
                {isExpanded && (
                  <div className="ml-[10.5rem] mt-2 mb-3 rounded-lg border border-gray-200 overflow-hidden">
                    <table className="w-full text-xs">
                      <thead>
                        <tr className="bg-gray-50 text-gray-500">
                          <th className="px-3 py-1.5 text-left font-semibold">Site ID</th>
                          <th className="px-3 py-1.5 text-left font-semibold">Project</th>
                          <th className="px-3 py-1.5 text-left font-semibold">Region</th>
                          <th className="px-3 py-1.5 text-left font-semibold">Market</th>
                          <th className="px-3 py-1.5 text-left font-semibold">Area</th>
                          <th className="px-3 py-1.5 text-left font-semibold">Vendor</th>
                          <th className="px-3 py-1.5 text-left font-semibold">CX Start</th>
                        </tr>
                      </thead>
                      <tbody>
                        {w.sites.map((s: CxForecastSite) => (
                          <tr
                            key={`${s.site_id}-${s.project_id}`}
                            className="border-t border-gray-100 hover:bg-blue-50/40"
                          >
                            <td className="px-3 py-1.5 font-medium text-gray-700">{s.site_id}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.project_name}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.region}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.market}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.area}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.vendor}</td>
                            <td className="px-3 py-1.5 text-gray-600">{s.cx_start_date}</td>
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
