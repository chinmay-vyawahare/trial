"use client";

import React, { useEffect, useState, useCallback } from "react";
import { getWeeklyStatusDefault, getWeeklyStatusHistory } from "@/lib/api";
import type { WeeklyStatusResponse, WeekData, RegionalStatusCounts } from "@/lib/types";

interface Props {
  region: string[];
  market: string[];
  area: string[];
  siteId: string;
  vendor: string;
  userId: string;
  considerVendorCapacity: boolean;
  paceConstraintFlag: boolean;
  statusFilter: string;
  slaMode: string;
  slaDateFrom: string;
  slaDateTo: string;
  refreshKey: number;
}

const STATUS_CONFIG: { key: string; label: string; color: string; bg: string; border: string }[] = [
  { key: "ON TRACK", label: "On Track", color: "#22c55e", bg: "bg-emerald-50", border: "border-emerald-200" },
  { key: "IN PROGRESS", label: "In Progress", color: "#eab308", bg: "bg-amber-50", border: "border-amber-200" },
  { key: "CRITICAL", label: "Critical", color: "#ef4444", bg: "bg-red-50", border: "border-red-200" },
  { key: "Blocked", label: "Blocked", color: "#6b7280", bg: "bg-gray-50", border: "border-gray-200" },
  { key: "Excluded - Crew Shortage", label: "Crew Shortage", color: "#f97316", bg: "bg-orange-50", border: "border-orange-200" },
  { key: "Excluded - Pace Constraint", label: "Pace Constraint", color: "#a855f7", bg: "bg-purple-50", border: "border-purple-200" },
];

/** Aggregate status counts across all regions for a week */
function aggregateStatusCounts(regionalCounts: RegionalStatusCounts): Record<string, number> {
  const totals: Record<string, number> = {};
  for (const regionData of Object.values(regionalCounts)) {
    for (const [status, count] of Object.entries(regionData)) {
      totals[status] = (totals[status] || 0) + count;
    }
  }
  return totals;
}

export default function WeeklyStatusChart({
  region, market, area, siteId, vendor, userId,
  considerVendorCapacity, paceConstraintFlag, statusFilter,
  slaMode, slaDateFrom, slaDateTo, refreshKey,
}: Props) {
  const [data, setData] = useState<WeeklyStatusResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hoveredWeek, setHoveredWeek] = useState<string | null>(null);
  const [expandedWeeks, setExpandedWeeks] = useState<Set<string>>(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const commonFilters = {
        region: region.length ? region : undefined,
        market: market.length ? market : undefined,
        area: area.length ? area : undefined,
        site_id: siteId || undefined,
        vendor: vendor || undefined,
        user_id: userId || undefined,
        consider_vendor_capacity: considerVendorCapacity || undefined,
        pace_constraint_flag: paceConstraintFlag || undefined,
        status: statusFilter || undefined,
      };

      let res: WeeklyStatusResponse;
      if (slaMode === "history" && slaDateFrom && slaDateTo) {
        res = await getWeeklyStatusHistory({
          date_from: slaDateFrom,
          date_to: slaDateTo,
          ...commonFilters,
        });
      } else {
        res = await getWeeklyStatusDefault(commonFilters);
      }
      setData(res);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load weekly status");
    } finally {
      setLoading(false);
    }
  }, [region, market, area, siteId, vendor, userId, considerVendorCapacity, paceConstraintFlag, statusFilter, slaMode, slaDateFrom, slaDateTo]);

  useEffect(() => {
    load();
  }, [load, refreshKey]);

  const maxTotal = data ? Math.max(...data.weeks.map((w) => w.total), 1) : 1;
  const totalSites = data ? data.weeks.reduce((a, w) => a + w.total, 0) : 0;
  const toggleWeekExpand = (weekKey: string) => {
    setExpandedWeeks((prev) => {
      const next = new Set(prev);
      if (next.has(weekKey)) next.delete(weekKey);
      else next.add(weekKey);
      return next;
    });
  };

  return (
    <div className="h-full overflow-auto p-5 space-y-5">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <h2 className="text-sm font-bold text-gray-800">Weekly Status Summary</h2>
          {data && (
            <span className="px-2.5 py-0.5 text-[10px] font-bold rounded-full bg-blue-50 text-blue-700 border border-blue-200">
              {data.sla_type.toUpperCase()} SLA
            </span>
          )}
          {data && data.date_from && (
            <span className="text-[10px] text-gray-400">
              {data.date_from} to {data.date_to}
            </span>
          )}
        </div>
        <button
          onClick={load}
          disabled={loading}
          className="px-3 py-1 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "Loading..." : "Refresh"}
        </button>
      </div>

      {loading && (
        <div className="flex items-center justify-center py-20">
          <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
        </div>
      )}

      {!loading && error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-600">{error}</div>
      )}

      {!loading && !error && (!data || data.weeks.length === 0) && (
        <div className="flex items-center justify-center py-20 text-gray-400 text-sm">
          No weekly status data available. Click &quot;Create Gantt Chart&quot; first.
        </div>
      )}

      {!loading && !error && data && data.weeks.length > 0 && <>
        {/* Summary row */}
        <div className="grid grid-cols-7 gap-3">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm px-4 py-3 text-center">
            <div className="text-2xl font-extrabold text-gray-800">{data.weeks.length}</div>
            <div className="text-[10px] font-bold uppercase text-gray-400 mt-0.5">Weeks</div>
          </div>
          {STATUS_CONFIG.map((sc) => {
            const total = data.weeks.reduce((a, w) => {
              const agg = aggregateStatusCounts(w.status_counts);
              return a + (agg[sc.key] || 0);
            }, 0);
            return (
              <div key={sc.key} className={`${sc.bg} rounded-xl border ${sc.border} shadow-sm px-4 py-3 text-center`}>
                <div className="text-2xl font-extrabold" style={{ color: sc.color }}>{total}</div>
                <div className="text-[10px] font-bold uppercase text-gray-400 mt-0.5">{sc.label}</div>
              </div>
            );
          })}
        </div>

        {/* Legend */}
        <div className="flex items-center gap-4 flex-wrap">
          {STATUS_CONFIG.map((sc) => (
            <div key={sc.key} className="flex items-center gap-1.5">
              <div className="w-3 h-3 rounded" style={{ background: sc.color }} />
              <span className="text-[10px] font-medium text-gray-500">{sc.label}</span>
            </div>
          ))}
        </div>

        {/* Stacked bar chart */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <h3 className="text-xs font-semibold text-gray-600 mb-4">
            Week-by-Week Site Status Distribution
          </h3>

          <div className="space-y-1.5">
            {data.weeks.map((w: WeekData) => {
              const weekKey = `${w.year}-W${String(w.week).padStart(2, "0")}`;
              const isHovered = hoveredWeek === weekKey;
              const isExpanded = expandedWeeks.has(weekKey);
              const aggCounts = aggregateStatusCounts(w.status_counts);
              const regions = Object.keys(w.status_counts).sort();

              return (
                <div key={weekKey}>
                  <div
                    className={`flex items-center gap-3 rounded-lg py-1.5 px-2 transition-colors cursor-pointer ${isHovered ? "bg-blue-50/60" : ""}`}
                    onMouseEnter={() => setHoveredWeek(weekKey)}
                    onMouseLeave={() => setHoveredWeek(null)}
                    onClick={() => toggleWeekExpand(weekKey)}
                  >
                    {/* Expand indicator */}
                    <div className="w-4 shrink-0 text-gray-400 text-[10px]">
                      {regions.length > 1 ? (isExpanded ? "▼" : "▶") : ""}
                    </div>

                    {/* Week label */}
                    <div className="w-20 shrink-0 text-right">
                      <div className="text-[11px] font-semibold text-gray-700">W{w.week}</div>
                      <div className="text-[9px] text-gray-400">{w.year}</div>
                    </div>

                    {/* Date range */}
                    <div className="w-32 shrink-0">
                      <div className="text-[10px] text-gray-400">{w.week_start}</div>
                      <div className="text-[10px] text-gray-400">{w.week_end}</div>
                    </div>

                    {/* Stacked bar */}
                    <div className="flex-1 h-8 bg-gray-50 rounded-lg overflow-hidden flex">
                      {STATUS_CONFIG.map((sc) => {
                        const count = aggCounts[sc.key] || 0;
                        if (count === 0) return null;
                        const pct = (count / maxTotal) * 100;
                        return (
                          <div
                            key={sc.key}
                            className="h-full flex items-center justify-center transition-all duration-300 relative group"
                            style={{
                              width: `${Math.max(pct, 2)}%`,
                              background: sc.color,
                            }}
                            title={`${sc.label}: ${count}`}
                          >
                            {pct > 6 && (
                              <span className="text-[9px] font-bold text-white drop-shadow-sm">
                                {count}
                              </span>
                            )}
                          </div>
                        );
                      })}
                    </div>

                    {/* Total badge */}
                    <div className="w-12 shrink-0 text-right">
                      <span className="text-xs font-bold text-gray-700">{w.total}</span>
                    </div>
                  </div>

                  {/* Region breakdown rows */}
                  {isExpanded && regions.length > 1 && regions.map((rgn) => {
                    const regionCounts = w.status_counts[rgn] || {};
                    const regionTotal = Object.values(regionCounts).reduce((a, b) => a + b, 0);
                    if (regionTotal === 0) return null;

                    return (
                      <div
                        key={`${weekKey}-${rgn}`}
                        className="flex items-center gap-3 rounded-lg py-1 px-2 ml-6 bg-gray-50/50"
                      >
                        <div className="w-4 shrink-0" />
                        <div className="w-20 shrink-0 text-right">
                          <div className="text-[10px] font-medium text-blue-600">{rgn}</div>
                        </div>
                        <div className="w-32 shrink-0" />
                        <div className="flex-1 h-5 bg-gray-100 rounded-md overflow-hidden flex">
                          {STATUS_CONFIG.map((sc) => {
                            const count = regionCounts[sc.key] || 0;
                            if (count === 0) return null;
                            const pct = (count / maxTotal) * 100;
                            return (
                              <div
                                key={sc.key}
                                className="h-full flex items-center justify-center"
                                style={{
                                  width: `${Math.max(pct, 2)}%`,
                                  background: sc.color,
                                  opacity: 0.8,
                                }}
                                title={`${rgn} - ${sc.label}: ${count}`}
                              >
                                {pct > 8 && (
                                  <span className="text-[8px] font-bold text-white drop-shadow-sm">
                                    {count}
                                  </span>
                                )}
                              </div>
                            );
                          })}
                        </div>
                        <div className="w-12 shrink-0 text-right">
                          <span className="text-[10px] font-semibold text-gray-500">{regionTotal}</span>
                        </div>
                      </div>
                    );
                  })}
                </div>
              );
            })}
          </div>
        </div>

        {/* Detail table */}
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
          <div className="px-5 py-3 border-b border-gray-100">
            <h3 className="text-xs font-semibold text-gray-600">
              Detailed Breakdown ({totalSites} total sites across {data.weeks.length} weeks)
            </h3>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead>
                <tr className="bg-gray-50">
                  <th className="px-4 py-2.5 text-left font-semibold text-gray-500">Week</th>
                  <th className="px-4 py-2.5 text-left font-semibold text-gray-500">Region</th>
                  <th className="px-4 py-2.5 text-left font-semibold text-gray-500">Date Range</th>
                  <th className="px-4 py-2.5 text-center font-semibold text-gray-500">Total</th>
                  {STATUS_CONFIG.map((sc) => (
                    <th key={sc.key} className="px-3 py-2.5 text-center font-semibold" style={{ color: sc.color }}>
                      {sc.label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.weeks.map((w: WeekData) => {
                  const weekKey = `${w.year}-W${String(w.week).padStart(2, "0")}`;
                  const regions = Object.keys(w.status_counts).sort();
                  const aggCounts = aggregateStatusCounts(w.status_counts);

                  return (
                    <React.Fragment key={weekKey}>
                      {/* Week total row */}
                      <tr className="border-t border-gray-100 bg-gray-50/50 hover:bg-blue-50/30 transition-colors">
                        <td className="px-4 py-2.5 font-semibold text-gray-700" rowSpan={1}>
                          W{w.week} <span className="text-gray-400 font-normal">{w.year}</span>
                        </td>
                        <td className="px-4 py-2.5 font-semibold text-gray-600">All Regions</td>
                        <td className="px-4 py-2.5 text-gray-500">
                          {w.week_start} &mdash; {w.week_end}
                        </td>
                        <td className="px-4 py-2.5 text-center font-bold text-gray-800">{w.total}</td>
                        {STATUS_CONFIG.map((sc) => {
                          const count = aggCounts[sc.key] || 0;
                          const pct = w.total > 0 ? Math.round((count / w.total) * 100) : 0;
                          return (
                            <td key={sc.key} className="px-3 py-2.5 text-center">
                              {count > 0 ? (
                                <div>
                                  <span className="font-bold" style={{ color: sc.color }}>{count}</span>
                                  <span className="text-gray-400 text-[10px] ml-1">{pct}%</span>
                                </div>
                              ) : (
                                <span className="text-gray-200">&mdash;</span>
                              )}
                            </td>
                          );
                        })}
                      </tr>
                      {/* Per-region rows */}
                      {regions.map((rgn) => {
                        const regionCounts = w.status_counts[rgn] || {};
                        const regionTotal = Object.values(regionCounts).reduce((a, b) => a + b, 0);
                        if (regionTotal === 0) return null;
                        return (
                          <tr key={`${weekKey}-${rgn}`} className="border-t border-gray-50 hover:bg-blue-50/20 transition-colors">
                            <td className="px-4 py-2" />
                            <td className="px-4 py-2 text-blue-600 font-medium">{rgn}</td>
                            <td className="px-4 py-2" />
                            <td className="px-4 py-2 text-center font-semibold text-gray-600">{regionTotal}</td>
                            {STATUS_CONFIG.map((sc) => {
                              const count = regionCounts[sc.key] || 0;
                              const pct = regionTotal > 0 ? Math.round((count / regionTotal) * 100) : 0;
                              return (
                                <td key={sc.key} className="px-3 py-2 text-center">
                                  {count > 0 ? (
                                    <div>
                                      <span className="font-semibold" style={{ color: sc.color }}>{count}</span>
                                      <span className="text-gray-400 text-[10px] ml-1">{pct}%</span>
                                    </div>
                                  ) : (
                                    <span className="text-gray-200">&mdash;</span>
                                  )}
                                </td>
                              );
                            })}
                          </tr>
                        );
                      })}
                    </React.Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </>}
    </div>
  );
}
