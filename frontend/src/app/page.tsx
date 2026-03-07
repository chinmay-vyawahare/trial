"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import { SiteGantt, DashboardSummary, FilterOptions } from "@/lib/types";
import { getGanttCharts, getDashboardSummary, getAllFilters, getExportCsvUrl } from "@/lib/api";
import Sidebar from "@/components/Sidebar";
import TopBar from "@/components/TopBar";
import SummaryCards from "@/components/SummaryCards";
import TabBar, { TimelineView } from "@/components/TabBar";
import GanttView from "@/components/GanttView";
import PrerequisitesView from "@/components/PrerequisitesView";
import AnalyticsView from "@/components/AnalyticsView";
import ChatPanel from "@/components/ChatPanel";
import AdminPanel from "@/components/AdminPanel";

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
  });
  const [loading, setLoading] = useState(true);
  const [region, setRegion] = useState("");
  const [market, setMarket] = useState("");
  const [area, setArea] = useState("");
  const [siteIdFilter, setSiteIdFilter] = useState("");
  const [vendor, setVendor] = useState("");
  const [siteFilter, setSiteFilter] = useState("");
  const [activeTab, setActiveTab] = useState("gantt");
  const [timelineView, setTimelineView] = useState<TimelineView>("week");
  const [expandedSites, setExpandedSites] = useState<Set<string>>(new Set());
  const [expandedVendors, setExpandedVendors] = useState<Set<string>>(
    new Set()
  );

  // Load filter options once on mount
  useEffect(() => {
    getAllFilters()
      .then(setFilterOptions)
      .catch((e) => console.error("Failed to load filters:", e));
  }, []);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const filters = {
        region: region || undefined,
        market: market || undefined,
        area: area || undefined,
        site_id: siteIdFilter || undefined,
        vendor: vendor || undefined,
      };

      const [ganttRes, dashRes] = await Promise.all([
        getGanttCharts(filters),
        getDashboardSummary(filters),
      ]);
      setSites(ganttRes.sites);
      setTotalCount(ganttRes.pagination.total_count);
      setDashboard(dashRes);
      // Auto-expand first 2 vendors and first 3 sites
      const vendorNames = [
        ...new Set(ganttRes.sites.map((s) => s.vendor_name)),
      ];
      setExpandedVendors(new Set(vendorNames.slice(0, 2)));
      setExpandedSites(
        new Set(ganttRes.sites.slice(0, 3).map((s) => s.site_id))
      );
    } catch (e) {
      console.error("Failed to load data:", e);
    } finally {
      setLoading(false);
    }
  }, [region, market, area, siteIdFilter, vendor]);

  useEffect(() => {
    loadData();
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

  // Derive vendor groups from the flat sites list for the GanttView
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

  function handleExport() {
    const url = getExportCsvUrl({
      region: region || undefined,
      market: market || undefined,
      area: area || undefined,
    });
    window.open(url, "_blank");
  }

  return (
    <div className="h-screen flex flex-col overflow-hidden bg-gray-50">
      <TopBar />

      <div className="flex flex-1 overflow-hidden">
        <Sidebar
          regions={filterOptions.regions}
          markets={filterOptions.markets}
          areas={filterOptions.areas}
          siteIds={filterOptions.site_ids}
          vendors={filterOptions.vendors}
          selectedRegion={region}
          selectedMarket={market}
          selectedArea={area}
          selectedSiteId={siteIdFilter}
          selectedVendor={vendor}
          onRegionChange={setRegion}
          onMarketChange={setMarket}
          onAreaChange={setArea}
          onSiteIdChange={setSiteIdFilter}
          onVendorChange={setVendor}
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
            timelineView={timelineView}
            onTimelineViewChange={setTimelineView}
          />

          <div className="flex-1 overflow-hidden">
            {activeTab === "gantt" && (
              loading ? (
                <div className="flex items-center justify-center h-full">
                  <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
                </div>
              ) : (
                <GanttView
                  sites={filteredSites}
                  vendorNames={vendorNames}
                  expandedSites={expandedSites}
                  expandedVendors={expandedVendors}
                  onToggleSite={toggleSite}
                  onToggleVendor={toggleVendor}
                  timelineView={timelineView}
                />
              )
            )}
            {activeTab === "heatmap" && <PrerequisitesView />}
            {activeTab === "analytics" && <AnalyticsView />}
            {activeTab === "calendar" && (
              <div className="flex items-center justify-center h-full text-gray-400 text-sm">
                Calendar view coming soon.
              </div>
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
              <div className="flex items-center gap-1.5 ml-4">
                <div className="w-0.5 h-3 bg-blue-600" />
                <span className="text-gray-500">Today</span>
              </div>
            </div>
          )}
        </div>
      </div>
      <ChatPanel />
    </div>
  );
}
