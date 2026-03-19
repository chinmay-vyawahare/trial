"use client";

import { DashboardSummary } from "@/lib/types";

interface Props {
  data: DashboardSummary;
}

export default function SummaryCards({ data }: Props) {
  const total = data.total_sites;
  const onTrack = data.on_track_sites;
  const inProgress = data.in_progress_sites;
  const critical = data.critical_sites;
  const blocked = data.blocked_sites;
  const excludedCrew = data.excluded_crew_shortage_sites;
  const excludedPace = data.excluded_pace_constraint_sites;
  const paceMax = data.pace_constraint_max_sites;

  const cards = [
    { label: "TOTAL SITES", value: total, sub: "Scheduled", bg: "bg-white", border: "border-gray-200", valueColor: "text-gray-900" },
    { label: "ON TRACK", value: onTrack, sub: `${total > 0 ? Math.round((onTrack / total) * 100) : 0}%`, bg: "bg-emerald-50", border: "border-emerald-200", valueColor: "text-emerald-600" },
    { label: "IN PROGRESS", value: inProgress, sub: `${total > 0 ? Math.round((inProgress / total) * 100) : 0}%`, bg: "bg-amber-50", border: "border-amber-200", valueColor: "text-amber-600" },
    { label: "CRITICAL", value: critical, sub: `${total > 0 ? Math.round((critical / total) * 100) : 0}%`, bg: "bg-red-50", border: "border-red-200", valueColor: "text-red-600" },
    { label: "BLOCKED", value: blocked, sub: `${total > 0 ? Math.round((blocked / total) * 100) : 0}%`, bg: "bg-gray-50", border: "border-gray-200", valueColor: "text-gray-600" },
    { label: "CREW SHORTAGE", value: excludedCrew, sub: "Excluded", bg: "bg-orange-50", border: "border-orange-200", valueColor: "text-orange-600" },
    { label: "PACE CONSTRAINT", value: excludedPace, sub: `Max ${paceMax}`, bg: "bg-purple-50", border: "border-purple-200", valueColor: "text-purple-600" },
  ];

  return (
    <div className="flex items-center gap-4 px-5 py-3 bg-white border-b border-gray-200">
      {cards.map((c) => (
        <div key={c.label} className={`text-center px-4 py-2 rounded-xl border ${c.bg} ${c.border}`}>
          <div className="text-[9px] font-bold tracking-wider uppercase text-gray-400">{c.label}</div>
          <div className={`text-2xl font-extrabold ${c.valueColor}`}>{c.value}</div>
          <div className="text-[10px] text-gray-400">{c.sub}</div>
        </div>
      ))}

      {/* Overall status badge */}
      {data.dashboard_status && (
        <div className="ml-auto text-center">
          <div className="text-[9px] font-bold tracking-wider uppercase text-gray-400 mb-1">STATUS</div>
          <span className={`px-3 py-1.5 text-xs font-bold rounded-full border ${
            data.dashboard_status === "ON TRACK"
              ? "bg-emerald-50 text-emerald-700 border-emerald-300"
              : data.dashboard_status === "IN PROGRESS"
              ? "bg-amber-50 text-amber-700 border-amber-300"
              : "bg-red-50 text-red-700 border-red-300"
          }`}>
            {data.dashboard_status}
          </span>
        </div>
      )}
    </div>
  );
}
