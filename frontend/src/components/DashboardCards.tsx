"use client";

import { DashboardSummary } from "@/lib/types";

interface Props {
  data: DashboardSummary;
}

export default function DashboardCards({ data }: Props) {
  const cards = [
    { label: "Total Sites", value: data.total_sites, color: "bg-blue-600" },
    { label: "On Track", value: data.on_track_sites, color: "bg-emerald-600" },
    { label: "In Progress", value: data.in_progress_sites, color: "bg-amber-500" },
    { label: "Critical", value: data.critical_sites, color: "bg-red-600" },
    { label: "Blocked", value: data.blocked_sites, color: "bg-gray-500" },
  ];

  return (
    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-4 mb-6">
      {cards.map((c) => (
        <div
          key={c.label}
          className={`${c.color} rounded-xl p-4 text-white shadow-lg`}
        >
          <div className="text-sm font-medium opacity-90">{c.label}</div>
          <div className="text-3xl font-bold mt-1">{c.value}</div>
        </div>
      ))}
    </div>
  );
}
