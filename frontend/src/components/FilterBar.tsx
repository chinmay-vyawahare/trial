"use client";

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
  onRegionChange: (v: string) => void;
  onMarketChange: (v: string) => void;
  onAreaChange: (v: string) => void;
  onSiteIdChange: (v: string) => void;
  onVendorChange: (v: string) => void;
  onApply: () => void;
  onClear: () => void;
  loading: boolean;
}

function MiniSelect({
  value,
  onChange,
  placeholder,
  options,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  options: string[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="px-2 py-1.5 text-[11px] rounded-lg border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400 min-w-[100px] max-w-[140px]"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}

export default function FilterBar({
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
  onApply,
  onClear,
  loading,
}: Props) {
  const hasFilters = selectedRegion || selectedMarket || selectedArea || selectedSiteId || selectedVendor;

  return (
    <div className="flex items-center gap-2 px-5 py-2 bg-gray-50 border-b border-gray-200 flex-wrap">
      <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400 mr-1">
        Filters
      </span>

      <MiniSelect value={selectedRegion} onChange={onRegionChange} placeholder="All Regions" options={regions} />
      <MiniSelect value={selectedArea} onChange={onAreaChange} placeholder="All Areas" options={areas} />
      <MiniSelect value={selectedMarket} onChange={onMarketChange} placeholder="All Markets" options={markets} />
      <MiniSelect value={selectedSiteId} onChange={onSiteIdChange} placeholder="All Sites" options={siteIds} />
      <MiniSelect value={selectedVendor} onChange={onVendorChange} placeholder="All Vendors" options={vendors} />

      <button
        onClick={onApply}
        disabled={loading}
        className="px-3 py-1.5 text-[11px] font-bold rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
      >
        {loading ? "Loading..." : "Apply"}
      </button>

      {hasFilters && (
        <button
          onClick={onClear}
          className="px-2.5 py-1.5 text-[11px] font-medium rounded-lg border border-gray-200 text-gray-500 bg-white hover:bg-gray-50"
        >
          Clear
        </button>
      )}
    </div>
  );
}
