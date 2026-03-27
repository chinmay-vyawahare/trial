"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { SiteGantt, DashboardSummary, FilterOptions, ChatAction } from "@/lib/types";
import { getGanttCharts, getDashboardSummary, getAllFilters, getExportCsvUrl, getExportCsvHistoryUrl, getSlaHistoryGantt, getUserFilters, saveUserFilters, deleteUserFilters } from "@/lib/api";
import Sidebar, { SlaMode } from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import SummaryCards from "@/components/SummaryCards";
import TabBar, { TimelineView } from "@/components/TabBar";
import GanttView from "@/components/GanttView";
import ChatPanel from "@/components/ChatPanel";
import AdminPanel from "@/components/AdminPanel";
import UserExpectedDays from "@/components/UserExpectedDays";
import UserPaceConstraints from "@/components/UserPaceConstraints";
import PrerequisiteFlowchart from "@/components/PrerequisiteFlowchart";
import PendingMilestonesChart from "@/components/PendingMilestonesChart";
import CxForecastChart from "@/components/CxForecastChart";
import CxActualChart from "@/components/CxActualChart";
import CalendarView from "@/components/CalendarView";
import WeeklyStatusChart from "@/components/WeeklyStatusChart";

export default function Home() {
  const [sites, setSites] = useState<SiteGantt[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [dashboard, setDashboard] = useState<DashboardSummary | null>(null);
  const [filterOptions, setFilterOptions] = useState<FilterOptions>({
    regions: [],
    markets: [],
    areas: [],
    site_ids: [],
    vendors: [],
    plan_types: [],
    dev_initiatives: [],
  });
  const [loading, setLoading] = useState(false);
  const [region, setRegion] = useState<string[]>([]);
  const [market, setMarket] = useState<string[]>([]);
  const [area, setArea] = useState<string[]>([]);
  const [siteIdFilter, setSiteIdFilter] = useState("");
  const [vendor, setVendor] = useState("");
  const [planType, setPlanType] = useState("");
  const [devInitiative, setDevInitiative] = useState("");
  const [slaMode, setSlaMode] = useState<SlaMode>("default");
  const [slaDateFrom, setSlaDateFrom] = useState("");
  const [slaDateTo, setSlaDateTo] = useState("");
  const [siteFilter, setSiteFilter] = useState("");
  const [activeTab, setActiveTab] = useState("gantt");
  const [timelineView, setTimelineView] = useState<TimelineView>("week");
  const [expandedSites, setExpandedSites] = useState<Set<string>>(new Set());
  const [expandedVendors, setExpandedVendors] = useState<Set<string>>(
    new Set()
  );
  const [userId, setUserId] = useState("");
  const [slaLastUpdated, setSlaLastUpdated] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState("");
  const [considerVendorCapacity, setConsiderVendorCapacity] = useState(false);
  const [paceConstraintFlag, setPaceConstraintFlag] = useState<boolean>(false);
  const initialLoad = useRef(true);
  const [analyticsRefreshKey, setAnalyticsRefreshKey] = useState(0);

  // Load filter options once on mount
  useEffect(() => {
    getAllFilters()
      .then(setFilterOptions)
      .catch((e) => console.error("Failed to load filters:", e));
  }, []);

  // When user applies a User ID, fetch their saved filters and auto-populate
  async function handleUserIdApply(newUserId: string) {
    setUserId(newUserId);
    if (!newUserId) return;
    try {
      const uf = await getUserFilters(newUserId);
      // region/market/area may be stored as JSON arrays in DB
      if (uf.region) {
        try { setRegion(JSON.parse(uf.region)); } catch { setRegion([uf.region]); }
      }
      if (uf.market) {
        try { setMarket(JSON.parse(uf.market)); } catch { setMarket([uf.market]); }
      }
      if (uf.area) {
        try { setArea(JSON.parse(uf.area)); } catch { setArea([uf.area]); }
      }
      if (uf.site_id) setSiteIdFilter(uf.site_id);
      if (uf.vendor) setVendor(uf.vendor);
      if (uf.plan_type_include) setPlanType(uf.plan_type_include);
      if (uf.regional_dev_initiatives) setDevInitiative(uf.regional_dev_initiatives);
    } catch (e) {
      console.error("No saved filters for user:", e);
    }
  }

  // Load gantt data — called on initial mount and when user clicks "Create Gantt Chart"
  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const filters = {
        region: region.length ? region : undefined,
        market: market.length ? market : undefined,
        area: area.length ? area : undefined,
        site_id: siteIdFilter || undefined,
        vendor: vendor || undefined,
        user_id: userId || undefined,
        consider_vendor_capacity: considerVendorCapacity || undefined,
        pace_constraint_flag: paceConstraintFlag || undefined,
        status: statusFilter || undefined,
      };

      let ganttRes;

      if (slaMode === "history" && slaDateFrom && slaDateTo) {
        const [historyRes, dashRes] = await Promise.all([
          getSlaHistoryGantt({
            date_from: slaDateFrom,
            date_to: slaDateTo,
            region: region.length ? region : undefined,
            market: market.length ? market : undefined,
            area: area.length ? area : undefined,
            site_id: siteIdFilter || undefined,
            vendor: vendor || undefined,
            user_id: userId || undefined,
            consider_vendor_capacity: considerVendorCapacity || undefined,
            pace_constraint_flag: paceConstraintFlag || undefined,
            status: statusFilter || undefined,
          }),
          getDashboardSummary(filters),
        ]);
        ganttRes = historyRes;
        setDashboard(dashRes);
        setSlaLastUpdated(historyRes.sla_last_updated);
      } else {
        const [defaultRes, dashRes] = await Promise.all([
          getGanttCharts(filters),
          getDashboardSummary(filters),
        ]);
        ganttRes = defaultRes;
        setDashboard(dashRes);
        setSlaLastUpdated(null);
      }

      setSites(ganttRes.sites);
      setTotalCount(ganttRes.pagination.total_count);
      // Auto-expand first 2 vendors and first 3 sites
      const vendorNames = [
        ...new Set(ganttRes.sites.map((s: SiteGantt) => s.vendor_name)),
      ];
      setExpandedVendors(new Set(vendorNames.slice(0, 2)));
      setExpandedSites(
        new Set(ganttRes.sites.slice(0, 3).map((s: SiteGantt) => s.site_id))
      );
    } catch (e) {
      console.error("Failed to load data:", e);
    } finally {
      setLoading(false);
      setAnalyticsRefreshKey((k) => k + 1);
    }
  }, [region, market, area, siteIdFilter, vendor, userId, slaMode, slaDateFrom, slaDateTo, considerVendorCapacity, paceConstraintFlag, statusFilter]);

  // Auto-load only on first mount
  useEffect(() => {
    if (initialLoad.current) {
      initialLoad.current = false;
      loadData();
    }
  }, [loadData]);

  const filteredSites = useMemo(() => {
    if (!siteFilter || siteFilter === "all") return sites;
    const q = siteFilter.toLowerCase();
    return sites.filter(
      (s) =>
        s.site_id.toLowerCase().includes(q) ||
        s.project_name.toLowerCase().includes(q)
    );
  }, [sites, siteFilter]);

  const vendorNames = useMemo(() => {
    const names = new Set<string>();
    for (const s of filteredSites) names.add(s.vendor_name || "Unassigned");
    return [...names].sort();
  }, [filteredSites]);

  function toggleSite(siteId: string) {
    setExpandedSites((prev) => {
      const next = new Set(prev);
      if (next.has(siteId)) next.delete(siteId);
      else next.add(siteId);
      return next;
    });
  }

  function toggleVendor(vendorName: string) {
    setExpandedVendors((prev) => {
      const next = new Set(prev);
      if (next.has(vendorName)) next.delete(vendorName);
      else next.add(vendorName);
      return next;
    });
  }

  function expandAll() {
    setExpandedVendors(new Set(vendorNames));
    setExpandedSites(new Set(filteredSites.map((s) => s.site_id)));
  }

  function collapseAll() {
    setExpandedVendors(new Set());
    setExpandedSites(new Set());
  }

  async function handleChatActions(actions: ChatAction[]) {
    for (const action of actions) {
      if (action.method === "POST" && action.endpoint.includes("/user-filters")) {
        // AI assistant asked to save/update filters via the unified endpoint
        const p = action.params as Record<string, unknown>;
        const uid = (p.user_id as string) || userId;
        if (!uid) continue;

        // Parse list params — they may arrive as arrays or comma-separated strings
        const toList = (v: unknown): string[] | undefined => {
          if (Array.isArray(v)) return v as string[];
          if (typeof v === "string") return [v];
          return undefined;
        };

        const regionList = toList(p.region);
        const marketList = toList(p.market);
        const areaList = toList(p.area);
        const ptiList = toList(p.plan_type_include);

        try {
          // 1. Save the changed filters to the backend
          await saveUserFilters({
            user_id: uid,
            region: regionList ?? undefined,
            market: marketList ?? undefined,
            area: areaList ?? undefined,
            site_id: (p.site_id as string) ?? undefined,
            vendor: (p.vendor as string) ?? undefined,
            plan_type_include: ptiList ?? undefined,
            regional_dev_initiatives: (p.regional_dev_initiatives as string) ?? undefined,
          });

          // 2. Re-fetch ALL saved filters so UI reflects the full state
          const uf = await getUserFilters(uid);

          // Helper: parse a JSON-array string or wrap a plain string
          const parseList = (v: string | null): string[] => {
            if (!v) return [];
            try { return JSON.parse(v); } catch { return [v]; }
          };

          setRegion(parseList(uf.region));
          setMarket(parseList(uf.market));
          setArea(parseList(uf.area));
          setSiteIdFilter(uf.site_id ?? "");
          setVendor(uf.vendor ?? "");
          setPlanType(uf.plan_type_include ?? "");
          setDevInitiative(uf.regional_dev_initiatives ?? "");
          setUserId(uid);

          // 3. Reload data with the updated filters
          setActiveTab("gantt");
          setTimeout(() => loadData(), 100);
        } catch (e) {
          console.error("Failed to save/fetch user filters:", e);
        }
      } else if (action.method === "GET" && action.endpoint.includes("/gantt-charts")) {
        // Apply filters from the action params and reload
        if (action.params.region) setRegion(Array.isArray(action.params.region) ? action.params.region : [action.params.region]);
        if (action.params.market) setMarket(Array.isArray(action.params.market) ? action.params.market : [action.params.market]);
        if (action.params.area) setArea(Array.isArray(action.params.area) ? action.params.area : [action.params.area]);
        if (action.params.site_id) setSiteIdFilter(action.params.site_id);
        if (action.params.vendor) setVendor(action.params.vendor);
        if (action.params.user_id) setUserId(action.params.user_id);
        // Switch to gantt tab and trigger reload
        setActiveTab("gantt");
        setTimeout(() => loadData(), 100);
      } else if (action.method === "DELETE" && action.endpoint.includes("/user-filters/")) {
        // AI assistant asked to clear filters
        clearFilters();
        setActiveTab("gantt");
        setTimeout(() => loadData(), 100);
      } else if (action.method === "GET" && action.endpoint.includes("/user-filters/")) {
        // Extract user_id from endpoint and fetch their filters
        const uid = action.params.user_id || action.endpoint.split("/").pop();
        if (uid) handleUserIdApply(uid);
      }
    }
  }

  function clearFilters() {
    setRegion([]);
    setMarket([]);
    setArea([]);
    setSiteIdFilter("");
    setVendor("");
    setPlanType("");
    setDevInitiative("");
    setStatusFilter("");
    // Also wipe saved filters on the backend so they don't get merged back
    if (userId) {
      deleteUserFilters(userId).catch(() => {});
    }
  }

  function handleExport() {
    const commonFilters = {
      region: region.length ? region : undefined,
      market: market.length ? market : undefined,
      area: area.length ? area : undefined,
      site_id: siteIdFilter || undefined,
      vendor: vendor || undefined,
      user_id: userId || undefined,
      consider_vendor_capacity: considerVendorCapacity || undefined,
      pace_constraint_flag: paceConstraintFlag || undefined,
      status: statusFilter || undefined,
    };
    const url = getExportCsvUrl(commonFilters);
    window.open(url, "_blank");
  }

  function handleExportHistory() {
    if (!slaDateFrom || !slaDateTo) return;
    const url = getExportCsvHistoryUrl({
      date_from: slaDateFrom,
      date_to: slaDateTo,
      region: region.length ? region : undefined,
      market: market.length ? market : undefined,
      area: area.length ? area : undefined,
      site_id: siteIdFilter || undefined,
      vendor: vendor || undefined,
      user_id: userId || undefined,
      consider_vendor_capacity: considerVendorCapacity || undefined,
      pace_constraint_flag: paceConstraintFlag || undefined,
      status: statusFilter || undefined,
    });
    window.open(url, "_blank");
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-gray-50">
      <TopBar userId={userId} onUserIdApply={handleUserIdApply} />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          regions={filterOptions.regions}
          markets={filterOptions.markets}
          areas={filterOptions.areas}
          siteIds={filterOptions.site_ids}
          vendors={filterOptions.vendors}
          planTypes={filterOptions.plan_types}
          devInitiatives={filterOptions.dev_initiatives}
          selectedRegion={region}
          selectedMarket={market}
          selectedArea={area}
          selectedSiteId={siteIdFilter}
          selectedVendor={vendor}
          selectedPlanType={planType}
          selectedDevInitiative={devInitiative}
          slaMode={slaMode}
          slaDateFrom={slaDateFrom}
          slaDateTo={slaDateTo}
          onRegionChange={setRegion}
          onMarketChange={setMarket}
          onAreaChange={setArea}
          onSiteIdChange={setSiteIdFilter}
          onVendorChange={setVendor}
          onPlanTypeChange={setPlanType}
          onDevInitiativeChange={setDevInitiative}
          onSlaModeChange={setSlaMode}
          onSlaDateFromChange={setSlaDateFrom}
          onSlaDateToChange={setSlaDateTo}
          considerVendorCapacity={considerVendorCapacity}
          onConsiderVendorCapacityChange={setConsiderVendorCapacity}
          paceConstraintFlag={paceConstraintFlag}
          onPaceConstraintFlagChange={setPaceConstraintFlag}
          selectedStatus={statusFilter}
          onStatusChange={setStatusFilter}
          userId={userId}
          onApply={loadData}
          onClear={clearFilters}
          loading={loading}
          totalSites={totalCount}
        />

        <div className="flex-1 flex flex-col overflow-hidden">
          {dashboard && <SummaryCards data={dashboard} />}

          <TabBar
            activeTab={activeTab}
            onTabChange={setActiveTab}
            siteFilter={siteFilter}
            onSiteFilterChange={setSiteFilter}
            onExpandAll={expandAll}
            onCollapseAll={collapseAll}
            onExport={handleExport}
            onExportHistory={handleExportHistory}
            showHistoryExport={slaMode === "history" && !!slaDateFrom && !!slaDateTo}
            timelineView={timelineView}
            onTimelineViewChange={setTimelineView}
          />

          <div className="flex-1 overflow-hidden">
            {activeTab === "gantt" && (
              loading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
                </div>
              ) : sites.length > 0 ? (
                <GanttView
                  sites={filteredSites}
                  vendorNames={vendorNames}
                  expandedSites={expandedSites}
                  expandedVendors={expandedVendors}
                  onToggleSite={toggleSite}
                  onToggleVendor={toggleVendor}
                  timelineView={timelineView}
                />
              ) : (
                <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                  Select filters and click &quot;Create Gantt Chart&quot; to load data.
                </div>
              )
            )}
            {activeTab === "flowchart" && <PrerequisiteFlowchart />}
            {activeTab === "expected-days" && <UserExpectedDays userId={userId} />}
            {activeTab === "pace-constraints" && <UserPaceConstraints userId={userId} />}
            {activeTab === "analytics" && (
              <PendingMilestonesChart
                region={region}
                market={market}
                area={area}
                siteId={siteIdFilter}
                vendor={vendor}
                userId={userId}
                considerVendorCapacity={considerVendorCapacity}
                paceConstraintFlag={paceConstraintFlag}
                slaMode={slaMode}
                slaDateFrom={slaDateFrom}
                slaDateTo={slaDateTo}
                refreshKey={analyticsRefreshKey}
              />
            )}
            {activeTab === "weekly-status" && (
              <WeeklyStatusChart
                region={region}
                market={market}
                area={area}
                siteId={siteIdFilter}
                vendor={vendor}
                userId={userId}
                considerVendorCapacity={considerVendorCapacity}
                paceConstraintFlag={paceConstraintFlag}
                statusFilter={statusFilter}
                slaMode={slaMode}
                slaDateFrom={slaDateFrom}
                slaDateTo={slaDateTo}
                refreshKey={analyticsRefreshKey}
              />
            )}
            {activeTab === "cx-forecast" && (
              <CxForecastChart
                region={region}
                market={market}
                area={area}
                siteId={siteIdFilter}
                vendor={vendor}
                userId={userId}
                refreshKey={analyticsRefreshKey}
              />
            )}
            {activeTab === "cx-actual" && (
              <CxActualChart
                region={region}
                market={market}
                area={area}
                siteId={siteIdFilter}
                vendor={vendor}
                userId={userId}
                refreshKey={analyticsRefreshKey}
              />
            )}
            {activeTab === "calendar" && (
              <CalendarView
                region={region}
                market={market}
                area={area}
                siteId={siteIdFilter}
                vendor={vendor}
                userId={userId}
                considerVendorCapacity={considerVendorCapacity}
                paceConstraintFlag={paceConstraintFlag}
                statusFilter={statusFilter}
                slaType={slaMode}
                refreshKey={analyticsRefreshKey}
              />
            )}
            {activeTab === "admin" && <AdminPanel />}
          </div>

          {/* Legend — only show on gantt tab */}
          {activeTab === "gantt" && (
            <div className="px-5 py-2 flex items-center gap-6 text-xs bg-white border-t border-gray-200">
              <div className="flex items-center gap-1.5">
                <div
                  className="w-4 h-2.5 rounded"
                  style={{ background: "#22c55e" }}
                />
                <span className="text-gray-500">On Track</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div
                  className="w-4 h-2.5 rounded"
                  style={{ background: "#eab308" }}
                />
                <span className="text-gray-500">In Progress</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div
                  className="w-4 h-2.5 rounded"
                  style={{ background: "#ef4444" }}
                />
                <span className="text-gray-500">Delayed</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div
                  className="w-4 h-2.5 rounded"
                  style={{ background: "#f97316" }}
                />
                <span className="text-gray-500">Excluded - Crew Shortage</span>
              </div>
              <div className="flex items-center gap-1.5">
                <div
                  className="w-4 h-2.5 rounded"
                  style={{ background: "#a855f7" }}
                />
                <span className="text-gray-500">Excluded - Pace Constraint</span>
              </div>
              <div className="flex items-center gap-1.5 ml-4">
                <div className="w-0.5 h-3 bg-blue-600" />
                <span className="text-gray-500">Today</span>
              </div>
              {slaLastUpdated && (
                <div className="flex items-center gap-1.5 ml-auto">
                  <span className="text-gray-400">SLA History Last Updated:</span>
                  <span className="text-gray-600 font-medium">
                    {new Date(slaLastUpdated).toLocaleString()}
                  </span>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
      <ChatPanel userId={userId} onActions={handleChatActions} />
    </div>
  );
}
