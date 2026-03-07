"use client";

import { useState, useMemo } from "react";

interface Props {
  regions: string[];
  markets: string[];
  areas: string[];
  siteIds: string[];
  vendors: string[];
  selectedRegion: string;
  selectedMarket: string;
  selectedArea: string;
  selectedSiteId: string;
  selectedVendor: string;
  onRegionChange: (r: string) => void;
  onMarketChange: (m: string) => void;
  onAreaChange: (a: string) => void;
  onSiteIdChange: (s: string) => void;
  onVendorChange: (v: string) => void;
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
  selectedRegion,
  selectedMarket,
  selectedArea,
  selectedSiteId,
  selectedVendor,
  onRegionChange,
  onMarketChange,
  onAreaChange,
  onSiteIdChange,
  onVendorChange,
  totalSites,
}: Props) {
  const [siteSearch, setSiteSearch] = useState("");

  const filteredSiteIds = useMemo(() => {
    if (!siteSearch) return siteIds.slice(0, 50);
    const q = siteSearch.toLowerCase();
    return siteIds.filter((id) => id.toLowerCase().includes(q)).slice(0, 50);
  }, [siteIds, siteSearch]);

  return (
    <aside className="w-56 flex-shrink-0 bg-gray-50 border-r border-gray-200 flex flex-col overflow-hidden">
      <div className="p-3 space-y-3 flex-1 overflow-y-auto">
        <div className="text-[10px] font-bold tracking-widest uppercase text-gray-400 flex items-center gap-1.5">
          <div className="w-1.5 h-1.5 rounded-full bg-blue-500" />
          Filters
        </div>

        {/* Region list */}
        <div>
          <Label>Region</Label>
          <div className="border border-gray-200 rounded-lg bg-white max-h-40 overflow-y-auto">
            <button
              onClick={() => onRegionChange("")}
              className={`w-full text-left px-2.5 py-1.5 text-xs border-b border-gray-100 transition-colors ${
                !selectedRegion
                  ? "bg-blue-50 text-blue-700 font-semibold"
                  : "text-gray-700 hover:bg-gray-50"
              }`}
            >
              All Regions
            </button>
            {regions.map((r) => (
              <button
                key={r}
                onClick={() => onRegionChange(r === selectedRegion ? "" : r)}
                className={`w-full text-left px-2.5 py-1.5 text-xs border-b border-gray-50 transition-colors ${
                  selectedRegion === r
                    ? "bg-blue-50 text-blue-700 font-semibold"
                    : "text-gray-700 hover:bg-gray-50"
                }`}
              >
                {r}
              </button>
            ))}
          </div>
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

        {/* Site ID search + select */}
        <div>
          <Label>Site ID</Label>
          <input
            type="text"
            placeholder="Search site..."
            value={siteSearch}
            onChange={(e) => setSiteSearch(e.target.value)}
            className="w-full px-2.5 py-1.5 text-xs rounded-lg border border-gray-200 bg-white text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400 mb-1"
          />
          <div className="border border-gray-200 rounded-lg bg-white max-h-32 overflow-y-auto">
            <button
              onClick={() => {
                onSiteIdChange("");
                setSiteSearch("");
              }}
              className={`w-full text-left px-2.5 py-1.5 text-xs border-b border-gray-100 transition-colors ${
                !selectedSiteId
                  ? "bg-blue-50 text-blue-700 font-semibold"
                  : "text-gray-700 hover:bg-gray-50"
              }`}
            >
              All Sites
            </button>
            {filteredSiteIds.map((id) => (
              <button
                key={id}
                onClick={() => {
                  onSiteIdChange(id === selectedSiteId ? "" : id);
                  setSiteSearch("");
                }}
                className={`w-full text-left px-2.5 py-1.5 text-xs border-b border-gray-50 transition-colors ${
                  selectedSiteId === id
                    ? "bg-blue-50 text-blue-700 font-semibold"
                    : "text-gray-700 hover:bg-gray-50"
                }`}
              >
                {id}
              </button>
            ))}
          </div>
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
      </div>
    </aside>
  );
}
