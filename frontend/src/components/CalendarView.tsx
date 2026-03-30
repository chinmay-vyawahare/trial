"use client";

import { useEffect, useState, useCallback } from "react";
import { getCalendarSites } from "@/lib/api";
import type { SiteGantt } from "@/lib/types";

interface Props {
  region: string[];
  market: string[];
  area: string[];
  siteId: string;
  vendor: string;
  userId: string;
  considerVendorCapacity: boolean;
  paceConstraintFlag: boolean;
  strictPaceApply?: boolean;
  statusFilter: string;
  slaType: string;
  refreshKey: number;
}

interface CalendarDay {
  date: string;
  sites: SiteGantt[];
}

export default function CalendarView({
  region, market, area, siteId, vendor, userId,
  considerVendorCapacity, paceConstraintFlag, strictPaceApply, statusFilter, slaType,
  refreshKey,
}: Props) {
  const [data, setData] = useState<{ count: number; sites: SiteGantt[] } | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState(() => {
    const d = new Date();
    return d.toISOString().slice(0, 10);
  });
  const [endDate, setEndDate] = useState(() => {
    const d = new Date();
    d.setDate(d.getDate() + 30);
    return d.toISOString().slice(0, 10);
  });
  const [expandedDay, setExpandedDay] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!startDate || !endDate) return;
    setLoading(true);
    setError(null);
    try {
      const res = await getCalendarSites({
        start_date: startDate,
        end_date: endDate,
        region: region.length ? region : undefined,
        market: market.length ? market : undefined,
        area: area.length ? area : undefined,
        site_id: siteId || undefined,
        vendor: vendor || undefined,
        user_id: userId || undefined,
        consider_vendor_capacity: considerVendorCapacity || undefined,
        pace_constraint_flag: paceConstraintFlag || undefined,
        strict_pace_apply: strictPaceApply || undefined,
        status: statusFilter || undefined,
        sla_type: slaType !== "default" ? slaType : undefined,
      });
      setData(res);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load calendar");
    } finally {
      setLoading(false);
    }
  }, [startDate, endDate, region, market, area, siteId, vendor, userId, considerVendorCapacity, paceConstraintFlag, strictPaceApply, statusFilter, slaType]);

  useEffect(() => { load(); }, [refreshKey]);

  // Group sites by forecasted_cx_start_date
  const dayMap = new Map<string, SiteGantt[]>();
  if (data) {
    for (const site of data.sites) {
      const d = site.forecasted_cx_start_date?.slice(0, 10) || "Unknown";
      if (!dayMap.has(d)) dayMap.set(d, []);
      dayMap.get(d)!.push(site);
    }
  }
  const days: CalendarDay[] = [...dayMap.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([date, sites]) => ({ date, sites }));

  const statusColor: Record<string, string> = {
    "ON TRACK": "bg-green-100 text-green-700 border-green-200",
    "IN PROGRESS": "bg-yellow-100 text-yellow-700 border-yellow-200",
    "CRITICAL": "bg-red-100 text-red-700 border-red-200",
    "Blocked": "bg-gray-200 text-gray-700 border-gray-300",
  };

  return (
    <div className="h-full overflow-auto p-5">
      <div className="max-w-6xl mx-auto space-y-4">
        {/* Controls */}
        <div className="flex items-center gap-3 flex-wrap">
          <div>
            <label className="block text-[10px] font-bold uppercase text-gray-400 mb-1">Start Date</label>
            <input type="date" value={startDate} onChange={(e) => setStartDate(e.target.value)}
              className="px-2.5 py-1.5 text-xs rounded-lg border border-gray-200 bg-white" />
          </div>
          <div>
            <label className="block text-[10px] font-bold uppercase text-gray-400 mb-1">End Date</label>
            <input type="date" value={endDate} onChange={(e) => setEndDate(e.target.value)}
              className="px-2.5 py-1.5 text-xs rounded-lg border border-gray-200 bg-white" />
          </div>
          <div className="pt-4">
            <button onClick={load} disabled={loading}
              className="px-4 py-1.5 text-xs font-bold rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
              {loading ? "Loading..." : "Load Calendar"}
            </button>
          </div>
          {data && (
            <div className="pt-4 text-xs text-gray-500">
              {data.count} site{data.count !== 1 ? "s" : ""} found
            </div>
          )}
        </div>

        {error && (
          <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-600">{error}</div>
        )}

        {loading && (
          <div className="flex items-center justify-center py-12">
            <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
          </div>
        )}

        {!loading && data && days.length === 0 && (
          <div className="text-center text-gray-400 text-sm py-12">No sites found for this date range.</div>
        )}

        {/* Calendar grid */}
        {!loading && days.length > 0 && (
          <div className="space-y-2">
            {days.map((day) => {
              const isExpanded = expandedDay === day.date;
              return (
                <div key={day.date} className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
                  <button
                    onClick={() => setExpandedDay(isExpanded ? null : day.date)}
                    className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-50 transition-colors"
                  >
                    <div className="flex items-center gap-3">
                      <span className="text-sm font-bold text-gray-800">
                        {new Date(day.date + "T00:00:00").toLocaleDateString("en-US", { weekday: "short", month: "short", day: "numeric", year: "numeric" })}
                      </span>
                      <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                        {day.sites.length} site{day.sites.length !== 1 ? "s" : ""}
                      </span>
                    </div>
                    <span className="text-gray-400 text-xs">{isExpanded ? "Collapse" : "Expand"}</span>
                  </button>
                  {isExpanded && (
                    <div className="border-t border-gray-100">
                      <table className="w-full text-xs">
                        <thead className="bg-gray-50">
                          <tr>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500 uppercase">Site ID</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500 uppercase">Project</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500 uppercase">Region</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500 uppercase">Market</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500 uppercase">Area</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500 uppercase">Vendor</th>
                            <th className="px-3 py-2 text-left font-semibold text-gray-500 uppercase">Status</th>
                          </tr>
                        </thead>
                        <tbody>
                          {day.sites.map((s) => (
                            <tr key={s.site_id} className="border-t border-gray-50 hover:bg-gray-50">
                              <td className="px-3 py-2 font-mono font-medium text-blue-700">{s.site_id}</td>
                              <td className="px-3 py-2 text-gray-800">{s.project_name}</td>
                              <td className="px-3 py-2 text-gray-600">{s.region}</td>
                              <td className="px-3 py-2 text-gray-600">{s.market}</td>
                              <td className="px-3 py-2 text-gray-600">{s.area}</td>
                              <td className="px-3 py-2 text-gray-600">{s.vendor_name}</td>
                              <td className="px-3 py-2">
                                <div className="flex items-center gap-1.5">
                                  <span className={`px-2 py-0.5 text-[10px] font-semibold rounded-full border ${statusColor[s.overall_status] || "bg-gray-100 text-gray-600 border-gray-200"}`}>
                                    {s.exclude_reason || s.overall_status}
                                  </span>
                                  {s.milestone_range && (
                                    <span className="text-[9px] font-semibold text-gray-500">({s.milestone_range})</span>
                                  )}
                                </div>
                              </td>
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
        )}
      </div>
    </div>
  );
}
