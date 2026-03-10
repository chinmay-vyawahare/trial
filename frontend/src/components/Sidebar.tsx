"use client";

import React, { useState, useEffect } from "react";
import { PaceConstraintEntry } from "@/lib/types";
import { getPaceConstraints } from "@/lib/api";

export type SlaMode = "default" | "history";

interface Props {
  regions: string[];
  markets: string[];
  areas: string[];
  siteIds: string[];
  vendors: string[];
  planTypes: string[];
  devInitiatives: string[];
  selectedRegion: string;
  selectedMarket: string;
  selectedArea: string;
  selectedSiteId: string;
  selectedVendor: string;
  selectedPlanType: string;
  selectedDevInitiative: string;
  slaMode: SlaMode;
  slaDateFrom: string;
  slaDateTo: string;
  considerVendorCapacity: boolean;
  onConsiderVendorCapacityChange: (v: boolean) => void;
  paceConstraintId: number | null;
  onPaceConstraintIdChange: (id: number | null) => void;
  selectedStatus: string;
  onStatusChange: (s: string) => void;
  userId: string;
  onRegionChange: (r: string) => void;
  onMarketChange: (m: string) => void;
  onAreaChange: (a: string) => void;
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
  paceConstraintId,
  onPaceConstraintIdChange,
  selectedStatus,
  onStatusChange,
  userId,
  onApply,
  onClear,
  loading,
  totalSites,
}: Props) {
  const [paceConstraints, setPaceConstraints] = useState<PaceConstraintEntry[]>([]);

  useEffect(() => {
    if (userId) {
      getPaceConstraints(userId)
        .then(setPaceConstraints)
        .catch(() => setPaceConstraints([]));
    } else {
      setPaceConstraints([]);
    }
  }, [userId]);

  const fmtDate = (d: string) => {
    try { return new Date(d).toLocaleDateString("en-US", { month: "short", day: "numeric" }); } catch { return d; }
  };

  return (
    <aside className="w-56 flex-shrink-0 bg-gray-50 border-r border-gray-200 flex flex-col overflow-hidden">
      <div className="p-3 space-y-3 flex-1 overflow-y-auto">
        <div className="text-[10px] font-bold tracking-widest uppercase text-gray-400 flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
          Filters
        </div>

        {/* Region dropdown */}
        <div>
          <Label>Region</Label>
          <Select
            value={selectedRegion}
            onChange={(e) => onRegionChange(e.target.value)}
          >
            <option value="">All Regions</option>
            {regions.map((r) => (
              <option key={r} value={r}>
                {r}
              </option>
            ))}
          </Select>
        </div>

        {/* Area dropdown */}
        <div>
          <Label>Area</Label>
          <Select
            value={selectedArea}
            onChange={(e) => onAreaChange(e.target.value)}
          >
            <option value="">All Areas</option>
            {areas.map((a) => (
              <option key={a} value={a}>
                {a}
              </option>
            ))}
          </Select>
        </div>

        {/* Market dropdown */}
        <div>
          <Label>Market</Label>
          <Select
            value={selectedMarket}
            onChange={(e) => onMarketChange(e.target.value)}
          >
            <option value="">All Markets</option>
            {markets.map((m) => (
              <option key={m} value={m}>
                {m}
              </option>
            ))}
          </Select>
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
        {/* Pace Constraint Selector */}
        <div>
          <Label>Pace Constraint</Label>
          <select
            value={paceConstraintId ?? ""}
            onChange={(e) => {
              const val = e.target.value;
              onPaceConstraintIdChange(val ? Number(val) : null);
            }}
            className="w-full px-2.5 py-2 text-xs rounded-lg border border-gray-200 bg-white text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            <option value="">None</option>
            {paceConstraints.map((c) => (
              <option key={c.id} value={c.id}>
                {fmtDate(c.start_date)} – {fmtDate(c.end_date)} · {[c.market, c.area, c.region].filter(Boolean).join("/") || "All"} · Max {c.max_sites}
              </option>
            ))}
          </select>
          {userId && paceConstraints.length === 0 && (
            <p className="text-[9px] text-gray-400 mt-1 leading-tight">
              No constraints found. Add them in the Pace Constraints tab.
            </p>
          )}
          {!userId && (
            <p className="text-[9px] text-gray-400 mt-1 leading-tight">
              Enter a User ID to load pace constraints.
            </p>
          )}
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
