"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { SiteGantt, PendingMilestoneBucket, MilestonePendingSites } from "@/lib/types";
import {
  getPendingMilestonesAuto,
  getPendingMilestonesSlaHistory,
  getPendingByMilestoneAuto,
  getPendingByMilestoneSlaHistory,
  getDrilldownAuto,
  getDrilldownSlaHistory,
} from "@/lib/api";

interface Props {
  region?: string[];
  market?: string[];
  area?: string[];
  siteId?: string;
  vendor?: string;
  userId?: string;
  considerVendorCapacity?: boolean;
  paceConstraintFlag?: boolean;
  strictPaceApply?: boolean;
  slaMode: "default" | "history";
  slaDateFrom?: string;
  slaDateTo?: string;
  /** Incremented by parent when user clicks "Create Gantt Chart" to trigger reload */
  refreshKey?: number;
}

const BAR_COLORS = [
  "#22c55e", "#3b82f6", "#eab308", "#f97316", "#ef4444",
  "#a855f7", "#ec4899", "#14b8a6", "#64748b", "#84cc16",
];

export default function PendingMilestonesChart({
  region, market, area, siteId, vendor, userId,
  considerVendorCapacity, paceConstraintFlag, strictPaceApply,
  slaMode, slaDateFrom, slaDateTo,
  refreshKey,
}: Props) {
  // Date range filter for forecasted CX start date
  const [filterDateFrom, setFilterDateFrom] = useState("");
  const [filterDateTo, setFilterDateTo] = useState("");
  const [autoData, setAutoData] = useState<PendingMilestoneBucket[]>([]);
  const [autoTotalSites, setAutoTotalSites] = useState(0);
  const [autoBlockedSites, setAutoBlockedSites] = useState(0);
  const [historyData, setHistoryData] = useState<PendingMilestoneBucket[]>([]);
  const [historyTotalSites, setHistoryTotalSites] = useState(0);
  const [historyBlockedSites, setHistoryBlockedSites] = useState(0);
  const [autoByMs, setAutoByMs] = useState<MilestonePendingSites[]>([]);
  const [autoByMsTotalSites, setAutoByMsTotalSites] = useState(0);
  const [autoByMsBlockedSites, setAutoByMsBlockedSites] = useState(0);
  const [historyByMs, setHistoryByMs] = useState<MilestonePendingSites[]>([]);
  const [historyByMsTotalSites, setHistoryByMsTotalSites] = useState(0);
  const [historyByMsBlockedSites, setHistoryByMsBlockedSites] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Drilldown state
  const [drilldownSites, setDrilldownSites] = useState<SiteGantt[] | null>(null);
  const [drilldownTitle, setDrilldownTitle] = useState("");
  const [drilldownLoading, setDrilldownLoading] = useState(false);

  const filters = useMemo(() => ({
    region: region?.length ? region : undefined,
    market: market?.length ? market : undefined,
    area: area?.length ? area : undefined,
    site_id: siteId || undefined,
    vendor: vendor || undefined,
    user_id: userId || undefined,
    consider_vendor_capacity: considerVendorCapacity || undefined,
    pace_constraint_flag: paceConstraintFlag || undefined,
    strict_pace_apply: strictPaceApply || undefined,
    filter_date_from: filterDateFrom || undefined,
    filter_date_to: filterDateTo || undefined,
  }), [region, market, area, siteId, vendor, userId, considerVendorCapacity, paceConstraintFlag, strictPaceApply, filterDateFrom, filterDateTo]);

  const loadData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [autoRes, autoMsRes] = await Promise.all([
        getPendingMilestonesAuto(filters),
        getPendingByMilestoneAuto(filters),
      ]);
      setAutoData(autoRes.pending_milestones);
      setAutoTotalSites(autoRes.total_sites);
      setAutoBlockedSites(autoRes.blocked_sites ?? 0);
      setAutoByMs(autoMsRes.milestones);
      setAutoByMsTotalSites(autoMsRes.total_sites);
      setAutoByMsBlockedSites(autoMsRes.blocked_sites ?? 0);

      if (slaMode === "history" && slaDateFrom && slaDateTo) {
        const historyFilters = { date_from: slaDateFrom, date_to: slaDateTo, ...filters };
        const [histRes, histMsRes] = await Promise.all([
          getPendingMilestonesSlaHistory(historyFilters),
          getPendingByMilestoneSlaHistory(historyFilters),
        ]);
        setHistoryData(histRes.pending_milestones);
        setHistoryTotalSites(histRes.total_sites);
        setHistoryBlockedSites(histRes.blocked_sites ?? 0);
        setHistoryByMs(histMsRes.milestones);
        setHistoryByMsTotalSites(histMsRes.total_sites);
        setHistoryByMsBlockedSites(histMsRes.blocked_sites ?? 0);
      } else {
        setHistoryData([]);
        setHistoryTotalSites(0);
        setHistoryBlockedSites(0);
        setHistoryByMs([]);
        setHistoryByMsTotalSites(0);
        setHistoryByMsBlockedSites(0);
      }
    } catch (e) {
      setError("Failed to load analytics data");
      console.error(e);
    } finally {
      setLoading(false);
    }
  }, [filters, slaMode, slaDateFrom, slaDateTo]);

  // Reload when parent signals (user clicks "Create Gantt Chart"), on first mount, or when date filters change
  useEffect(() => {
    loadData();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [refreshKey, filterDateFrom, filterDateTo]);

  // Drilldown handlers
  const handleBucketClick = useCallback(async (pendingCount: number, isHistory: boolean) => {
    setDrilldownLoading(true);
    setDrilldownTitle(
      pendingCount === 0
        ? "Completed Sites (0 pending milestones)"
        : `Sites with ${pendingCount} Pending Milestone${pendingCount > 1 ? "s" : ""}`
    );
    setDrilldownSites([]);
    try {
      const params = { drilldown_type: "pending_count" as const, pending_count: pendingCount, ...filters };
      const res = isHistory && slaDateFrom && slaDateTo
        ? await getDrilldownSlaHistory({ date_from: slaDateFrom, date_to: slaDateTo, ...params })
        : await getDrilldownAuto(params);
      setDrilldownSites(res.sites);
    } catch (e) {
      console.error(e);
      setDrilldownSites(null);
    } finally {
      setDrilldownLoading(false);
    }
  }, [filters, slaDateFrom, slaDateTo]);

  const handleMilestoneClick = useCallback(async (msKey: string, msName: string, isHistory: boolean) => {
    setDrilldownLoading(true);
    setDrilldownTitle(`Sites Pending: ${msName}`);
    setDrilldownSites([]);
    try {
      const params = { drilldown_type: "milestone_key" as const, milestone_key: msKey, ...filters };
      const res = isHistory && slaDateFrom && slaDateTo
        ? await getDrilldownSlaHistory({ date_from: slaDateFrom, date_to: slaDateTo, ...params })
        : await getDrilldownAuto(params);
      setDrilldownSites(res.sites);
    } catch (e) {
      console.error(e);
      setDrilldownSites(null);
    } finally {
      setDrilldownLoading(false);
    }
  }, [filters, slaDateFrom, slaDateTo]);

  const closeDrilldown = () => setDrilldownSites(null);

  // Get unique milestone names from drilldown sites (exclude virtual milestones)
  const VIRTUAL_KEYS = new Set(["all_prereq", "cx_start_forecast"]);
  const milestoneNames = useMemo(() => {
    if (!drilldownSites || drilldownSites.length === 0) return [];
    const seen = new Map<string, { key: string; name: string; order: number }>();
    for (const site of drilldownSites) {
      for (const m of site.milestones) {
        if (!VIRTUAL_KEYS.has(m.key) && !seen.has(m.key)) {
          seen.set(m.key, { key: m.key, name: m.name, order: m.sort_order });
        }
      }
    }
    return [...seen.values()].sort((a, b) => a.order - b.order);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [drilldownSites]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-red-500 text-sm">
        {error}
      </div>
    );
  }

  return (
    <>
      <div className="h-full overflow-y-auto p-5 space-y-6">
        {/* Date range filter */}
        <div className="flex items-center gap-3 bg-white rounded-xl shadow border border-gray-200 px-5 py-3">
          <span className="text-xs font-semibold text-gray-600">Forecast CX Start Date Range</span>
          <div className="flex items-center gap-2 ml-auto">
            <label className="text-xs text-gray-400">From</label>
            <input
              type="date"
              value={filterDateFrom}
              onChange={(e) => setFilterDateFrom(e.target.value)}
              className="px-2 py-1 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            <label className="text-xs text-gray-400">To</label>
            <input
              type="date"
              value={filterDateTo}
              onChange={(e) => setFilterDateTo(e.target.value)}
              className="px-2 py-1 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
            />
            {(filterDateFrom || filterDateTo) && (
              <button
                onClick={() => { setFilterDateFrom(""); setFilterDateTo(""); }}
                className="px-2 py-1 text-xs rounded-lg bg-gray-100 text-gray-500 hover:bg-gray-200 transition-colors"
              >
                Clear
              </button>
            )}
          </div>
        </div>

        {/* Pending count distribution */}
        <BucketBarChart
          title="Pending Milestones — Auto / User Override SLA"
          data={autoData}
          totalSites={autoTotalSites}
          blockedSites={autoBlockedSites}
          subtitle="Based on default or user-override expected days"
          onBarClick={(count) => handleBucketClick(count, false)}
        />
        {slaMode === "history" && historyData.length > 0 && (
          <BucketBarChart
            title="Pending Milestones — SLA History (Median)"
            data={historyData}
            totalSites={historyTotalSites}
            blockedSites={historyBlockedSites}
            subtitle={`Based on historical median (${slaDateFrom} to ${slaDateTo})`}
            onBarClick={(count) => handleBucketClick(count, true)}
          />
        )}

        {/* Per-milestone pending site count */}
        <MilestoneBarChart
          title="Pending Sites by Milestone — Auto / User Override SLA"
          data={autoByMs}
          totalSites={autoByMsTotalSites}
          blockedSites={autoByMsBlockedSites}
          subtitle="Number of sites pending per milestone"
          onBarClick={(key, name) => handleMilestoneClick(key, name, false)}
        />
        {slaMode === "history" && historyByMs.length > 0 && (
          <MilestoneBarChart
            title="Pending Sites by Milestone — SLA History (Median)"
            data={historyByMs}
            totalSites={historyByMsTotalSites}
            blockedSites={historyByMsBlockedSites}
            subtitle={`Number of sites pending per milestone (${slaDateFrom} to ${slaDateTo})`}
            onBarClick={(key, name) => handleMilestoneClick(key, name, true)}
          />
        )}
      </div>

      {/* Drilldown Modal */}
      {drilldownSites !== null && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40" onClick={closeDrilldown}>
          <div className="bg-white rounded-2xl shadow-2xl w-[92vw] h-[85vh] flex flex-col overflow-hidden" onClick={(e) => e.stopPropagation()}>
            {/* Header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-200 shrink-0">
              <div>
                <h2 className="text-sm font-bold text-gray-800">{drilldownTitle}</h2>
                <p className="text-xs text-gray-400 mt-0.5">{drilldownSites.length} site{drilldownSites.length !== 1 ? "s" : ""}</p>
              </div>
              <button
                onClick={closeDrilldown}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-gray-100 text-gray-600 hover:bg-gray-200 transition-colors"
              >
                Close
              </button>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-auto">
              {drilldownLoading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
                </div>
              ) : drilldownSites.length > 0 ? (
                <table className="w-full text-xs border-collapse">
                  <thead className="sticky top-0 z-10 bg-gray-50">
                    <tr className="border-b border-gray-200">
                      <th className="text-left px-3 py-2.5 font-semibold text-gray-500 whitespace-nowrap">Site ID</th>
                      <th className="text-left px-3 py-2.5 font-semibold text-gray-500 whitespace-nowrap">Project</th>
                      <th className="text-left px-3 py-2.5 font-semibold text-gray-500 whitespace-nowrap">Market</th>
                      <th className="text-left px-3 py-2.5 font-semibold text-gray-500 whitespace-nowrap">Vendor</th>
                      <th className="text-center px-3 py-2.5 font-semibold text-gray-500 whitespace-nowrap">Overall Status</th>
                      <th className="text-left px-3 py-2.5 font-semibold text-gray-500 whitespace-nowrap">Note</th>
                      {milestoneNames.map((ms) => (
                        <th key={ms.key} className="text-center px-2 py-2.5 font-semibold text-gray-500 whitespace-nowrap min-w-[80px]">
                          {ms.name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {drilldownSites.map((site) => {
                      const msMap = new Map(site.milestones.map((m) => [m.key, m]));
                      return (
                        <tr key={site.site_id} className="border-b border-gray-100 hover:bg-gray-50">
                          <td className="px-3 py-2 font-medium text-gray-800 whitespace-nowrap">{site.site_id}</td>
                          <td className="px-3 py-2 text-gray-600 whitespace-nowrap max-w-[180px] truncate" title={site.project_name}>{site.project_name}</td>
                          <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{site.market}</td>
                          <td className="px-3 py-2 text-gray-600 whitespace-nowrap">{site.vendor_name || "—"}</td>
                          <td className="px-3 py-2 text-center">
                            <div className="flex items-center justify-center gap-1">
                              <StatusBadge status={site.overall_status} />
                              {site.milestone_range && (
                                <span className="text-[9px] font-semibold text-gray-500">({site.milestone_range})</span>
                              )}
                            </div>
                          </td>
                          <td className="px-3 py-2 text-gray-600 whitespace-nowrap">
                            {site.note && (
                              <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full border mr-1 ${
                                site.note === "Ready for schedule"
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-300"
                                  : "bg-amber-50 text-amber-700 border-amber-300"
                              }`}>
                                {site.note}
                              </span>
                            )}
                            {site.exclude_reason && (
                              <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full border bg-orange-50 text-orange-700 border-orange-300">
                                {site.exclude_reason}
                              </span>
                            )}
                            {!site.note && !site.exclude_reason && "—"}
                          </td>
                          {milestoneNames.map((ms) => {
                            const m = msMap.get(ms.key);
                            if (!m) return <td key={ms.key} className="px-2 py-2 text-center text-gray-300">—</td>;
                            return (
                              <td key={ms.key} className="px-2 py-2 text-center">
                                <MilestoneStatusDot status={m.status} actualFinish={m.actual_finish} />
                              </td>
                            );
                          })}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              ) : (
                <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                  No sites found for this selection.
                </div>
              )}
            </div>

            {/* Legend */}
            <div className="px-5 py-2.5 flex items-center gap-5 text-xs border-t border-gray-200 shrink-0 bg-white">
              <span className="text-gray-400 font-medium">Milestone Status:</span>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
                <span className="text-gray-500">On Track</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-amber-500" />
                <span className="text-gray-500">In Progress</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-2.5 h-2.5 rounded-full bg-red-500" />
                <span className="text-gray-500">Delayed</span>
              </div>
              <div className="flex items-center gap-1.5 ml-3">
                <span className="text-gray-400">|</span>
              </div>
              <span className="text-gray-400 font-medium">Overall:</span>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-2 rounded bg-emerald-100 border border-emerald-400" />
                <span className="text-gray-500">ON TRACK</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-2 rounded bg-amber-100 border border-amber-400" />
                <span className="text-gray-500">IN PROGRESS</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-2 rounded bg-red-100 border border-red-400" />
                <span className="text-gray-500">CRITICAL</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div className="w-3 h-2 rounded bg-gray-100 border border-gray-400" />
                <span className="text-gray-500">Blocked</span>
              </div>
            </div>
          </div>
        </div>
      )}
    </>
  );
}

/* ── Bucket bar chart (N pending → site count) ───────────────────── */

function BucketBarChart({
  title,
  data,
  totalSites,
  blockedSites,
  subtitle,
  onBarClick,
}: {
  title: string;
  data: PendingMilestoneBucket[];
  totalSites: number;
  blockedSites: number;
  subtitle: string;
  onBarClick: (pendingCount: number) => void;
}) {
  if (data.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow border border-gray-200 p-6">
        <h3 className="font-bold text-gray-800 text-sm">{title}</h3>
        <p className="text-xs text-gray-400 mt-1">{subtitle}</p>
        <div className="flex items-center justify-center h-32 text-gray-400 text-sm">
          No data available
        </div>
      </div>
    );
  }

  const allBuckets = data.map((d) => ({ pending: d.pending_milestone_count, sites: d.site_count }));
  const maxSiteCount = Math.max(...allBuckets.map((d) => d.sites), 1);

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-bold text-gray-800 text-sm">{title}</h3>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500 font-medium">
            Total Sites: {totalSites}
          </span>
          {blockedSites > 0 && (
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-300">
              Blocked: {blockedSites}
            </span>
          )}
        </div>
      </div>
      <p className="text-xs text-gray-400 mb-5">{subtitle}</p>

      <div className="space-y-3">
        {allBuckets.map((bucket, idx) => {
          const pct = bucket.sites > 0 ? (bucket.sites / maxSiteCount) * 100 : 0;
          const color = bucket.sites === 0 ? "#d1d5db" : BAR_COLORS[idx % BAR_COLORS.length];
          const clickable = bucket.sites > 0;
          return (
            <div
              key={bucket.pending}
              className={`group ${clickable ? "cursor-pointer" : ""}`}
              onClick={() => clickable && onBarClick(bucket.pending)}
            >
              <div className="flex items-center gap-3">
                <div className="w-28 shrink-0 text-right">
                  <span className={`text-xs font-semibold text-gray-700 ${clickable ? "group-hover:text-blue-600 transition-colors" : ""}`}>
                    {bucket.pending === 0 ? "Completed" : `${bucket.pending} pending`}
                  </span>
                </div>
                <div className={`flex-1 h-8 bg-gray-100 rounded-lg overflow-hidden relative ${clickable ? "group-hover:bg-gray-200 transition-colors" : ""}`}>
                  <div
                    className={`h-full rounded-lg transition-all duration-500 flex items-center ${clickable ? "group-hover:brightness-110" : ""}`}
                    style={{ width: bucket.sites > 0 ? `${Math.max(pct, 2)}%` : "0%", background: color }}
                  >
                    {pct > 15 && bucket.sites > 0 && (
                      <span className="text-white text-[11px] font-bold ml-2.5">
                        {bucket.sites} sites
                      </span>
                    )}
                  </div>
                  {(pct <= 15 || bucket.sites === 0) && (
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 text-[11px] font-bold text-gray-600">
                      {bucket.sites} sites
                    </span>
                  )}
                </div>
                <div className="w-12 text-right">
                  <span className="text-[11px] font-medium text-gray-500">
                    {totalSites > 0
                      ? `${Math.round((bucket.sites / totalSites) * 100)}%`
                      : "0%"}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-5 pt-4 border-t border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-3 h-3 rounded bg-gray-300" />
          <span className="text-xs text-gray-500">Click any bar to drill down into sites</span>
        </div>
        <span className="text-xs text-gray-500">
          Sum of all bars: <span className="font-semibold text-gray-700">{allBuckets.reduce((s, b) => s + b.sites, 0)}</span>
          {" "}= Total Sites: <span className="font-semibold text-gray-700">{totalSites}</span>
        </span>
      </div>
    </div>
  );
}

/* ── Milestone bar chart (milestone name → pending site count) ───── */

function MilestoneBarChart({
  title,
  data,
  totalSites,
  blockedSites,
  subtitle,
  onBarClick,
}: {
  title: string;
  data: MilestonePendingSites[];
  totalSites: number;
  blockedSites: number;
  subtitle: string;
  onBarClick: (milestoneKey: string, milestoneName: string) => void;
}) {
  if (data.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow border border-gray-200 p-6">
        <h3 className="font-bold text-gray-800 text-sm">{title}</h3>
        <p className="text-xs text-gray-400 mt-1">{subtitle}</p>
        <div className="flex items-center justify-center h-32 text-gray-400 text-sm">
          No data available
        </div>
      </div>
    );
  }

  const maxCount = Math.max(...data.map((d) => d.pending_site_count), 1);

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 p-6">
      <div className="flex items-center justify-between mb-1">
        <h3 className="font-bold text-gray-800 text-sm">{title}</h3>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-500 font-medium">
            Total Sites: {totalSites}
          </span>
          {blockedSites > 0 && (
            <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-gray-100 text-gray-600 border border-gray-300">
              Blocked: {blockedSites}
            </span>
          )}
        </div>
      </div>
      <p className="text-xs text-gray-400 mb-5">{subtitle}</p>

      <div className="space-y-3">
        {data.map((ms, idx) => {
          const pct = ms.pending_site_count > 0 ? (ms.pending_site_count / maxCount) * 100 : 0;
          const color = ms.pending_site_count === 0 ? "#d1d5db" : BAR_COLORS[idx % BAR_COLORS.length];
          const clickable = ms.pending_site_count > 0;
          return (
            <div
              key={ms.milestone_key}
              className={`group ${clickable ? "cursor-pointer" : ""}`}
              onClick={() => clickable && onBarClick(ms.milestone_key, ms.milestone_name)}
            >
              <div className="flex items-center gap-3">
                <div className="w-40 shrink-0 text-right">
                  <span
                    className={`text-xs font-semibold text-gray-700 truncate block ${clickable ? "group-hover:text-blue-600 transition-colors" : ""}`}
                    title={ms.milestone_name}
                  >
                    {ms.milestone_name}
                  </span>
                </div>
                <div className={`flex-1 h-8 bg-gray-100 rounded-lg overflow-hidden relative ${clickable ? "group-hover:bg-gray-200 transition-colors" : ""}`}>
                  <div
                    className={`h-full rounded-lg transition-all duration-500 flex items-center ${clickable ? "group-hover:brightness-110" : ""}`}
                    style={{
                      width: ms.pending_site_count > 0 ? `${Math.max(pct, 2)}%` : "0%",
                      background: color,
                    }}
                  >
                    {pct > 15 && ms.pending_site_count > 0 && (
                      <span className="text-white text-[11px] font-bold ml-2.5">
                        {ms.pending_site_count} / {totalSites} sites
                      </span>
                    )}
                  </div>
                  {(pct <= 15 || ms.pending_site_count === 0) && (
                    <span className="absolute left-2 top-1/2 -translate-y-1/2 text-[11px] font-bold text-gray-600">
                      {ms.pending_site_count} / {totalSites} sites
                    </span>
                  )}
                </div>
                <div className="w-12 text-right">
                  <span className="text-[11px] font-medium text-gray-500">
                    {totalSites > 0
                      ? `${Math.round((ms.pending_site_count / totalSites) * 100)}%`
                      : "0%"}
                  </span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-5 pt-4 border-t border-gray-100 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded bg-gray-300" />
            <span className="text-xs text-gray-500">0 pending = all sites completed this milestone</span>
          </div>
          <div className="flex items-center gap-2">
            <div className="w-3 h-3 rounded" style={{ background: BAR_COLORS[4] }} />
            <span className="text-xs text-gray-500">Click any bar to drill down into sites</span>
          </div>
        </div>
        <span className="text-xs text-gray-500">
          Total Sites: <span className="font-semibold text-gray-700">{totalSites}</span>
        </span>
      </div>
    </div>
  );
}

/* ── Helper components for drilldown table ────────────────────────── */

function StatusBadge({ status }: { status: string }) {
  const upper = status.toUpperCase();
  let bg = "bg-gray-100 text-gray-600 border-gray-300";
  if (upper === "ON TRACK") bg = "bg-emerald-50 text-emerald-700 border-emerald-300";
  else if (upper === "IN PROGRESS") bg = "bg-amber-50 text-amber-700 border-amber-300";
  else if (upper === "CRITICAL") bg = "bg-red-50 text-red-700 border-red-300";
  else if (upper === "BLOCKED") bg = "bg-gray-100 text-gray-600 border-gray-300";
  else if (upper.includes("CREW SHORTAGE")) bg = "bg-orange-50 text-orange-700 border-orange-300";
  else if (upper.includes("PACE CONSTRAINT")) bg = "bg-purple-50 text-purple-700 border-purple-300";

  return (
    <span className={`inline-block px-2 py-0.5 text-[10px] font-bold rounded border ${bg} whitespace-nowrap`}>
      {status}
    </span>
  );
}

function MilestoneStatusDot({ status, actualFinish }: { status: string; actualFinish: string | null }) {
  let dotColor = "bg-gray-300";
  let label = status;

  if (status === "On Track") dotColor = "bg-emerald-500";
  else if (status === "In Progress") dotColor = "bg-amber-500";
  else if (status === "Delayed") dotColor = "bg-red-500";

  return (
    <div className="flex flex-col items-center gap-0.5" title={`${status}${actualFinish ? ` (${actualFinish})` : ""}`}>
      <div className={`w-2.5 h-2.5 rounded-full ${dotColor}`} />
      <span className="text-[9px] text-gray-400 leading-none">{label}</span>
    </div>
  );
}
