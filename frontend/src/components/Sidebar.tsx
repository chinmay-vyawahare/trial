"use client";

import React from "react";

export type SlaMode = "default" | "history";

interface Props {
  regions: string[];
  markets: string[];
  areas: string[];
  siteIds: string[];
  vendors: string[];
  planTypes: string[];
  devInitiatives: string[];
  selectedRegion: string[];
  selectedMarket: string[];
  selectedArea: string[];
  selectedSiteId: string;
  selectedVendor: string;
  selectedPlanType: string;
  selectedDevInitiative: string;
  slaMode: SlaMode;
  slaDateFrom: string;
  slaDateTo: string;
  considerVendorCapacity: boolean;
  onConsiderVendorCapacityChange: (v: boolean) => void;
  paceConstraintFlag: boolean;
  onPaceConstraintFlagChange: (v: boolean) => void;
  strictPaceApply: boolean;
  onStrictPaceApplyChange: (v: boolean) => void;
  selectedStatus: string;
  onStatusChange: (s: string) => void;
  userId: string;
  onRegionChange: (r: string[]) => void;
  onMarketChange: (m: string[]) => void;
  onAreaChange: (a: string[]) => void;
  onSiteIdChange: (s: string) => void;
  onVendorChange: (v: string) => void;
  onPlanTypeChange: (p: string) => void;
  onDevInitiativeChange: (d: string) => void;
  onSlaModeChange: (m: SlaMode) => void;
  onSlaDateFromChange: (d: string) => void;
  onSlaDateToChange: (d: string) => void;
  onApply: () => void;
  onClear: () => void;
  loading: boolean;
  totalSites: number;
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="block text-[10px] font-bold tracking-wider uppercase text-gray-400 mb-1">
      {children}
    </label>
  );
}

function Select({
  value,
  onChange,
  children,
}: {
  value?: string;
  onChange?: (e: React.ChangeEvent<HTMLSelectElement>) => void;
  children: React.ReactNode;
}) {
  return (
    <select
      value={value}
      onChange={onChange}
      className="w-full px-2.5 py-2 text-xs rounded-lg border border-gray-200 bg-white text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
    >
      {children}
    </select>
  );
}

function MultiSelect({
  selected,
  onChange,
  options,
  placeholder,
}: {
  selected: string[];
  onChange: (v: string[]) => void;
  options: string[];
  placeholder: string;
}) {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef<HTMLDivElement>(null);

  React.useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  function toggle(val: string) {
    if (selected.includes(val)) onChange(selected.filter((v) => v !== val));
    else onChange([...selected, val]);
  }

  const label = selected.length === 0 ? placeholder : selected.length === 1 ? selected[0] : `${selected.length} selected`;

  return (
    <div ref={ref} className="relative">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full px-2.5 py-2 text-xs rounded-lg border border-gray-200 bg-white text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400 text-left truncate"
      >
        <span className={selected.length === 0 ? "text-gray-400" : ""}>{label}</span>
      </button>
      {open && (
        <div className="absolute z-50 mt-1 w-full max-h-48 overflow-y-auto bg-white border border-gray-200 rounded-lg shadow-lg">
          {selected.length > 0 && (
            <button
              type="button"
              onClick={() => { onChange([]); }}
              className="w-full px-2.5 py-1.5 text-[10px] text-red-500 hover:bg-red-50 text-left font-medium border-b border-gray-100"
            >
              Clear selection
            </button>
          )}
          {options.map((o) => (
            <label key={o} className="flex items-center gap-2 px-2.5 py-1.5 hover:bg-blue-50 cursor-pointer">
              <input
                type="checkbox"
                checked={selected.includes(o)}
                onChange={() => toggle(o)}
                className="accent-blue-500 w-3 h-3"
              />
              <span className="text-xs text-gray-700 truncate">{o}</span>
            </label>
          ))}
          {options.length === 0 && (
            <div className="px-2.5 py-2 text-xs text-gray-400">No options</div>
          )}
        </div>
      )}
    </div>
  );
}

export default function Sidebar({
  regions,
  markets,
  areas,
  siteIds,
  vendors,
  planTypes,
  devInitiatives,
  selectedRegion,
  selectedMarket,
  selectedArea,
  selectedSiteId,
  selectedVendor,
  selectedPlanType,
  selectedDevInitiative,
  slaMode,
  slaDateFrom,
  slaDateTo,
  onRegionChange,
  onMarketChange,
  onAreaChange,
  onSiteIdChange,
  onVendorChange,
  onPlanTypeChange,
  onDevInitiativeChange,
  onSlaModeChange,
  onSlaDateFromChange,
  onSlaDateToChange,
  considerVendorCapacity,
  onConsiderVendorCapacityChange,
  paceConstraintFlag,
  onPaceConstraintFlagChange,
  strictPaceApply,
  onStrictPaceApplyChange,
  selectedStatus,
  onStatusChange,
  userId,
  onApply,
  onClear,
  loading,
  totalSites,
}: Props) {

  return (
    <aside className="w-56 flex-shrink-0 bg-gray-50 border-r border-gray-200 flex flex-col overflow-hidden">
      <div className="p-3 space-y-3 flex-1 overflow-y-auto">
        <div className="text-[10px] font-bold tracking-widest uppercase text-gray-400 flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
          Filters
        </div>

        {/* Region multi-select */}
        <div>
          <Label>Region</Label>
          <MultiSelect selected={selectedRegion} onChange={onRegionChange} options={regions} placeholder="All Regions" />
        </div>

        {/* Area multi-select */}
        <div>
          <Label>Area</Label>
          <MultiSelect selected={selectedArea} onChange={onAreaChange} options={areas} placeholder="All Areas" />
        </div>

        {/* Market multi-select */}
        <div>
          <Label>Market</Label>
          <MultiSelect selected={selectedMarket} onChange={onMarketChange} options={markets} placeholder="All Markets" />
        </div>

        {/* Site ID dropdown */}
        <div>
          <Label>Site ID</Label>
          <Select
            value={selectedSiteId}
            onChange={(e) => onSiteIdChange(e.target.value)}
          >
            <option value="">All Sites</option>
            {siteIds.map((id) => (
              <option key={id} value={id}>
                {id}
              </option>
            ))}
          </Select>
        </div>

        {/* Sites count */}
        <div>
          <Label>No. of Sites</Label>
          <div className="px-2.5 py-2 text-sm font-bold rounded-lg border border-gray-200 bg-white text-gray-800">
            {totalSites}
          </div>
        </div>

        {/* Vendor */}
        <div>
          <Label>Vendor</Label>
          <Select
            value={selectedVendor}
            onChange={(e) => onVendorChange(e.target.value)}
          >
            <option value="">All Vendors</option>
            {vendors.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </Select>
        </div>

        {/* Status */}
        <div>
          <Label>Status</Label>
          <Select
            value={selectedStatus}
            onChange={(e) => onStatusChange(e.target.value)}
          >
            <option value="">All Statuses</option>
            <option value="ON TRACK">On Track</option>
            <option value="IN PROGRESS">In Progress</option>
            <option value="CRITICAL">Critical</option>
            <option value="Blocked">Blocked</option>
            <option value="Excluded - Crew Shortage">Excluded - Crew Shortage</option>
            <option value="Excluded - Pace Constraint">Excluded - Pace Constraint</option>
          </Select>
        </div>

        {/* POR Plan Type */}
        <div>
          <Label>POR Plan Type</Label>
          <Select
            value={selectedPlanType}
            onChange={(e) => onPlanTypeChange(e.target.value)}
          >
            <option value="">All Plan Types</option>
            {planTypes.map((pt) => (
              <option key={pt} value={pt}>
                {pt}
              </option>
            ))}
          </Select>
        </div>

        {/* Regional Dev Initiatives */}
        <div>
          <Label>Regional Dev Initiatives</Label>
          <Select
            value={selectedDevInitiative}
            onChange={(e) => onDevInitiativeChange(e.target.value)}
          >
            <option value="">All Initiatives</option>
            {devInitiatives.map((d) => (
              <option key={d} value={d}>
                {d}
              </option>
            ))}
          </Select>
        </div>

        {/* SLA Type */}
        <div>
          <Label>SLA Type</Label>
          <div className="flex items-center gap-0.5 bg-gray-100 rounded-lg p-0.5">
            <button
              onClick={() => onSlaModeChange("default")}
              className={`flex-1 px-2 py-1.5 text-[10px] font-semibold rounded-md transition-all ${
                slaMode === "default"
                  ? "bg-white text-blue-700 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              Default
            </button>
            <button
              onClick={() => onSlaModeChange("history")}
              className={`flex-1 px-2 py-1.5 text-[10px] font-semibold rounded-md transition-all ${
                slaMode === "history"
                  ? "bg-white text-blue-700 shadow-sm"
                  : "text-gray-500 hover:text-gray-700"
              }`}
            >
              History Based
            </button>
          </div>

          {slaMode === "history" && (
            <div className="mt-2 space-y-2">
              <div>
                <label className="block text-[10px] font-medium text-gray-400 mb-0.5">
                  Start Date
                </label>
                <input
                  type="date"
                  value={slaDateFrom}
                  onChange={(e) => onSlaDateFromChange(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-gray-200 bg-white text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
              </div>
              <div>
                <label className="block text-[10px] font-medium text-gray-400 mb-0.5">
                  End Date
                </label>
                <input
                  type="date"
                  value={slaDateTo}
                  onChange={(e) => onSlaDateToChange(e.target.value)}
                  className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-gray-200 bg-white text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
              </div>
            </div>
          )}
        </div>
        {/* Vendor Capacity Toggle */}
        <div>
          <label className="flex items-center gap-2 cursor-pointer">
            <input
              type="checkbox"
              checked={considerVendorCapacity}
              onChange={(e) => onConsiderVendorCapacityChange(e.target.checked)}
              className="rounded border-gray-300 text-blue-600 focus:ring-blue-400"
            />
            <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400">
              Consider Vendor Capacity
            </span>
          </label>
          <p className="text-[9px] text-gray-400 mt-1 leading-tight">
            Marks sites exceeding GC parallel capacity as excluded.
          </p>
        </div>
        {/* Pace Constraint Toggle */}
        <div>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={paceConstraintFlag}
              onChange={(e) => onPaceConstraintFlagChange(e.target.checked)}
              className="accent-blue-500 w-3.5 h-3.5"
            />
            <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400">
              Apply Pace Constraints
            </span>
          </label>
          <p className="text-[9px] text-gray-400 mt-1 leading-tight">
            Applies all pace constraints configured for this user.
          </p>
        </div>
        {/* Strict Pace Apply Toggle */}
        <div>
          <label className="flex items-center gap-2 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={strictPaceApply}
              onChange={(e) => onStrictPaceApplyChange(e.target.checked)}
              className="accent-blue-500 w-3.5 h-3.5"
            />
            <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400">
              Strict Pace (No Stretch)
            </span>
          </label>
          <p className="text-[9px] text-gray-400 mt-1 leading-tight">
            Excludes excess sites without pushing them to next week.
          </p>
        </div>
      </div>

      {/* Apply / Clear buttons */}
      <div className="p-3 border-t border-gray-200 bg-gray-50 space-y-2">
        <button
          onClick={onApply}
          disabled={loading}
          className="w-full px-3 py-2.5 text-xs font-bold rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors shadow-sm"
        >
          {loading ? (
            <span className="flex items-center justify-center gap-2">
              <span className="animate-spin w-3.5 h-3.5 border-2 border-white border-t-transparent rounded-full" />
              Loading...
            </span>
          ) : (
            "Create Gantt Chart"
          )}
        </button>
        <button
          onClick={onClear}
          className="w-full px-3 py-2 text-xs font-medium rounded-lg border border-gray-200 text-gray-500 bg-white hover:bg-gray-50 transition-colors"
        >
          Clear Filters
        </button>
      </div>
    </aside>
  );
}
