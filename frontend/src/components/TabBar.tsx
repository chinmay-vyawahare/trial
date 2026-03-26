"use client";

export type TimelineView = "day" | "week" | "month" | "quarter" | "year";

interface Props {
  activeTab: string;
  onTabChange: (tab: string) => void;
  siteFilter: string;
  onSiteFilterChange: (f: string) => void;
  onExpandAll: () => void;
  onCollapseAll: () => void;
  onExport: () => void;
  onExportHistory?: () => void;
  showHistoryExport?: boolean;
  timelineView: TimelineView;
  onTimelineViewChange: (v: TimelineView) => void;
}

const tabs = [
  { key: "gantt", label: "Gantt Chart" },
  { key: "flowchart", label: "Flowchart" },
  { key: "expected-days", label: "Expected Days" },
  { key: "pace-constraints", label: "Pace Constraints" },
  { key: "analytics", label: "Analytics" },
  { key: "weekly-status", label: "Weekly Status" },
  { key: "cx-forecast", label: "CX Forecast" },
  { key: "cx-actual", label: "CX Actual" },
  { key: "calendar", label: "Calendar" },
  { key: "admin", label: "Admin" },
];

const viewOptions: { key: TimelineView; label: string }[] = [
  { key: "day", label: "Day" },
  { key: "week", label: "Week" },
  { key: "month", label: "Month" },
  { key: "quarter", label: "Quarter" },
  { key: "year", label: "Year" },
];

export default function TabBar({
  activeTab,
  onTabChange,
  siteFilter,
  onSiteFilterChange,
  onExpandAll,
  onCollapseAll,
  onExport,
  onExportHistory,
  showHistoryExport,
  timelineView,
  onTimelineViewChange,
}: Props) {
  return (
    <div className="bg-white border-b border-gray-200">
      {/* Row 1: Tabs */}
      <div className="flex items-center gap-1 px-5 pt-2 pb-1.5 overflow-x-auto">
        {tabs.map((t) => (
          <button
            key={t.key}
            onClick={() => onTabChange(t.key)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors whitespace-nowrap ${
              activeTab === t.key
                ? "bg-blue-600 text-white shadow-sm"
                : "text-gray-500 hover:bg-gray-100 hover:text-gray-700"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Row 2: Controls — timeline toggle, search, actions */}
      <div className="flex items-center justify-between px-5 py-1.5 border-t border-gray-100">
        {/* Left: Timeline View Toggle */}
        <div className="flex items-center gap-0.5 bg-gray-100 rounded-lg p-0.5">
          {viewOptions.map((v) => (
            <button
              key={v.key}
              onClick={() => onTimelineViewChange(v.key)}
              className={`px-3 py-1 text-[11px] font-semibold rounded-md transition-all ${
                timelineView === v.key
                  ? "bg-white text-blue-700 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              {v.label}
            </button>
          ))}
        </div>

        {/* Right: Search + actions */}
        <div className="flex items-center gap-2">
          <label className="text-xs text-gray-400 font-medium">Filter:</label>
          <input
            type="text"
            placeholder="Search sites..."
            value={siteFilter}
            onChange={(e) => onSiteFilterChange(e.target.value)}
            className="px-2.5 py-1 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400 w-36"
          />
          <div className="w-px h-5 bg-gray-200" />
          <button
            onClick={onCollapseAll}
            className="px-2.5 py-1 text-[11px] font-medium rounded-lg border border-gray-200 text-gray-600 bg-white hover:bg-gray-50"
          >
            Collapse All
          </button>
          <button
            onClick={onExpandAll}
            className="px-2.5 py-1 text-[11px] font-medium rounded-lg border border-gray-200 text-gray-600 bg-white hover:bg-gray-50"
          >
            Expand All
          </button>
          <div className="w-px h-5 bg-gray-200" />
          <button
            onClick={onExport}
            className="px-2.5 py-1 text-[11px] font-medium rounded-lg border border-blue-200 text-blue-600 bg-blue-50 hover:bg-blue-100"
          >
            Export CSV
          </button>
          {showHistoryExport && onExportHistory && (
            <button
              onClick={onExportHistory}
              className="px-2.5 py-1 text-[11px] font-medium rounded-lg border border-purple-200 text-purple-600 bg-purple-50 hover:bg-purple-100"
            >
              Export SLA History CSV
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
