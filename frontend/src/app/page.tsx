"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import { SiteGantt, DashboardSummary, FilterOptions, ChatAction } from "@/lib/types";
import { getGanttCharts, getDashboardSummary, getAllFilters, getExportCsvUrl, getSlaHistoryGantt, getUserFilters, deleteUserFilters } from "@/lib/api";
import Sidebar, { SlaMode } from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import SummaryCards from "@/components/SummaryCards";
import TabBar, { TimelineView } from "@/components/TabBar";
import GanttView from "@/components/GanttView";
import ChatPanel from "@/components/ChatPanel";
import AdminPanel from "@/components/AdminPanel";
import UserExpectedDays from "@/components/UserExpectedDays";
import PrerequisiteFlowchart from "@/components/PrerequisiteFlowchart";
import DashboardSummaryPanel from "@/components/DashboardSummaryPanel";

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
  const [region, setRegion] = useState("");
  const [market, setMarket] = useState("");
  const [area, setArea] = useState("");
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
  const initialLoad = useRef(true);

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
      if (uf.region) setRegion(uf.region);
      if (uf.market) setMarket(uf.market);
      if (uf.area) setArea(uf.area);
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
        region: region || undefined,
        market: market || undefined,
        area: area || undefined,
        site_id: siteIdFilter || undefined,
        vendor: vendor || undefined,
        user_id: userId || undefined,
      };

      let ganttRes;

      if (slaMode === "history" && slaDateFrom && slaDateTo) {
        const [historyRes, dashRes] = await Promise.all([
          getSlaHistoryGantt({
            date_from: slaDateFrom,
            date_to: slaDateTo,
            region: region || undefined,
            market: market || undefined,
            area: area || undefined,
            site_id: siteIdFilter || undefined,
            vendor: vendor || undefined,
            user_id: userId || undefined,
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
    }
  }, [region, market, area, siteIdFilter, vendor, userId, slaMode, slaDateFrom, slaDateTo]);

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

  function handleChatActions(actions: ChatAction[]) {
    for (const action of actions) {
      if (action.method === "GET" && action.endpoint.includes("/gantt-charts")) {
        // Apply filters from the action params and reload
        if (action.params.region) setRegion(action.params.region);
        if (action.params.market) setMarket(action.params.market);
        if (action.params.area) setArea(action.params.area);
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
    setRegion("");
    setMarket("");
    setArea("");
    setSiteIdFilter("");
    setVendor("");
    setPlanType("");
    setDevInitiative("");
    // Also wipe saved filters on the backend so they don't get merged back
    if (userId) {
      deleteUserFilters(userId).catch(() => {});
    }
  }

  function handleExport() {
    const url = getExportCsvUrl({
      region: region || undefined,
      market: market || undefined,
      area: area || undefined,
      user_id: userId || undefined,
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
          onApply={loadData}
          onClear={clearFilters}
          loading={loading}
          totalSites={totalCount}
        />

        <div className="flex-1 flex flex-col overflow-hidden">
          {dashboard && <SummaryCards data={dashboard} />}

          <DashboardSummaryPanel
            regions={filterOptions.regions}
            markets={filterOptions.markets}
            areas={filterOptions.areas}
          />

          <TabBar
            activeTab={activeTab}
            onTabChange={setActiveTab}
            siteFilter={siteFilter}
            onSiteFilterChange={setSiteFilter}
            onExpandAll={expandAll}
            onCollapseAll={collapseAll}
            onExport={handleExport}
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
