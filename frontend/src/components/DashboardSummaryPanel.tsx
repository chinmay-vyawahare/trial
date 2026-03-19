"use client";

import { useEffect, useState, useCallback } from "react";
import { DashboardSummary } from "@/lib/types";
import { getDashboardSummary } from "@/lib/api";

interface Props {
  regions: string[];
  markets: string[];
  areas: string[];
}

function CircleProgress({
  value,
  total,
  color,
  label,
  size = 72,
  strokeWidth = 6,
}: {
  value: number;
  total: number;
  color: string;
  label: string;
  size?: number;
  strokeWidth?: number;
}) {
  const radius = (size - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const pct = total > 0 ? value / total : 0;
  const offset = circumference - pct * circumference;

  return (
    <div className="flex flex-col items-center gap-0.5">
      <div className="relative" style={{ width: size, height: size }}>
        <svg width={size} height={size} className="-rotate-90">
          <circle cx={size / 2} cy={size / 2} r={radius} fill="none" stroke="#e5e7eb" strokeWidth={strokeWidth} />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={color}
            strokeWidth={strokeWidth}
            strokeDasharray={circumference}
            strokeDashoffset={offset}
            strokeLinecap="round"
            className="transition-all duration-700 ease-out"
          />
        </svg>
        <div className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="text-sm font-extrabold text-gray-800">{value}</span>
          <span className="text-[8px] text-gray-400">{total > 0 ? Math.round(pct * 100) : 0}%</span>
        </div>
      </div>
      <span className="text-[9px] font-bold tracking-wider uppercase text-gray-500">{label}</span>
    </div>
  );
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
      className="px-2 py-1 text-[11px] rounded-md border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400 min-w-[90px]"
    >
      <option value="">{placeholder}</option>
      {options.map((o) => (
        <option key={o} value={o}>{o}</option>
      ))}
    </select>
  );
}

export default function DashboardSummaryPanel({ regions, markets, areas }: Props) {
  const [data, setData] = useState<DashboardSummary | null>(null);
  const [loading, setLoading] = useState(false);
  const [dsRegion, setDsRegion] = useState("");
  const [dsMarket, setDsMarket] = useState("");
  const [dsArea, setDsArea] = useState("");
  const [dsUserId, setDsUserId] = useState("");

  const fetchSummary = useCallback(async () => {
    setLoading(true);
    try {
      const res = await getDashboardSummary({
        region: dsRegion || undefined,
        market: dsMarket || undefined,
        area: dsArea || undefined,
        user_id: dsUserId || undefined,
      });
      setData(res);
    } catch (e) {
      console.error("Failed to load dashboard summary:", e);
    } finally {
      setLoading(false);
    }
  }, [dsRegion, dsMarket, dsArea, dsUserId]);

  // Fetch on mount
  useEffect(() => {
    fetchSummary();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div className="px-5 py-3 bg-white border-b border-gray-200">
      {/* Filters row */}
      <div className="flex items-center gap-2 mb-3 flex-wrap">
        <span className="text-[10px] font-bold tracking-wider uppercase text-gray-400 mr-1">
          Dashboard Summary
        </span>
        <MiniSelect value={dsRegion} onChange={setDsRegion} placeholder="All Regions" options={regions} />
        <MiniSelect value={dsMarket} onChange={setDsMarket} placeholder="All Markets" options={markets} />
        <MiniSelect value={dsArea} onChange={setDsArea} placeholder="All Areas" options={areas} />
        <input
          type="text"
          placeholder="User ID"
          value={dsUserId}
          onChange={(e) => setDsUserId(e.target.value)}
          className="px-2 py-1 text-[11px] rounded-md border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-blue-400 w-24"
        />
        <button
          onClick={fetchSummary}
          disabled={loading}
          className="px-3 py-1 text-[11px] font-bold rounded-md bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition-colors"
        >
          {loading ? "..." : "Load"}
        </button>
      </div>

      {/* Circles */}
      {loading && !data ? (
        <div className="flex items-center justify-center py-4">
          <div className="animate-spin w-5 h-5 border-2 border-blue-500 border-t-transparent rounded-full" />
        </div>
      ) : data ? (
        <div className="flex items-center gap-5 relative">
          {loading && (
            <div className="absolute top-0 right-0">
              <div className="animate-spin w-3 h-3 border-2 border-blue-400 border-t-transparent rounded-full" />
            </div>
          )}

          {/* Total */}
          <div className="flex flex-col items-center gap-0.5">
            <div
              className="relative flex items-center justify-center rounded-full border-[5px] border-blue-500"
              style={{ width: 72, height: 72 }}
            >
              <div className="flex flex-col items-center">
                <span className="text-xl font-extrabold text-gray-900">{data.total_sites}</span>
                <span className="text-[8px] text-gray-400">Sites</span>
              </div>
            </div>
            <span className="text-[9px] font-bold tracking-wider uppercase text-gray-500">Total</span>
          </div>

          <div className="w-px h-12 bg-gray-200" />

          <CircleProgress value={data.on_track_sites} total={data.total_sites} color="#22c55e" label="On Track" />
          <CircleProgress value={data.in_progress_sites} total={data.total_sites} color="#eab308" label="In Progress" />
          <CircleProgress value={data.critical_sites} total={data.total_sites} color="#ef4444" label="Critical" />
          <CircleProgress value={data.blocked_sites} total={data.total_sites} color="#6b7280" label="Blocked" />
          <CircleProgress value={data.excluded_crew_shortage_sites} total={data.total_sites} color="#f97316" label="Crew Shortage" />
          <CircleProgress value={data.excluded_pace_constraint_sites} total={data.total_sites} color="#a855f7" label="Pace Constraint" />

          {data.pace_constraint_max_sites > 0 && (
            <>
              <div className="w-px h-12 bg-gray-200" />
              <div className="flex flex-col items-center gap-0.5">
                <div
                  className="relative flex items-center justify-center rounded-full border-[5px] border-purple-400"
                  style={{ width: 72, height: 72 }}
                >
                  <div className="flex flex-col items-center">
                    <span className="text-xl font-extrabold text-gray-900">{data.pace_constraint_max_sites}</span>
                    <span className="text-[8px] text-gray-400">Max</span>
                  </div>
                </div>
                <span className="text-[9px] font-bold tracking-wider uppercase text-gray-500">Pace Max</span>
              </div>
            </>
          )}

          {data.dashboard_status && (
            <div className="ml-auto flex flex-col items-center gap-0.5">
              <span className="text-[8px] font-bold tracking-wider uppercase text-gray-400">Status</span>
              <span
                className={`px-3 py-1.5 text-xs font-bold rounded-full border ${
                  data.dashboard_status === "ON TRACK"
                    ? "bg-emerald-50 text-emerald-700 border-emerald-300"
                    : data.dashboard_status === "IN PROGRESS"
                    ? "bg-amber-50 text-amber-700 border-amber-300"
                    : "bg-red-50 text-red-700 border-red-300"
                }`}
              >
                {data.dashboard_status}
              </span>
            </div>
          )}
        </div>
      ) : null}
    </div>
  );
}
