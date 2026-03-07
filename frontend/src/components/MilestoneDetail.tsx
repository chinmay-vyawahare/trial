"use client";

import { Milestone, SiteGantt } from "@/lib/types";

interface Props {
  site: SiteGantt;
}

function getStatusColor(status: string): string {
  if (status === "On Track") return "#22c55e";
  if (status === "In Progress") return "#eab308";
  if (status === "Delayed") return "#ef4444";
  return "#94a3b8";
}

function statusIcon(status: string) {
  if (status === "On Track") return "✓";
  if (status === "Delayed") return "!";
  if (status === "In Progress") return "→";
  return "○";
}

function statusBg(status: string) {
  if (status === "On Track") return "bg-emerald-50 border-emerald-200";
  if (status === "Delayed") return "bg-red-50 border-red-200";
  if (status === "In Progress") return "bg-amber-50 border-amber-200";
  return "bg-gray-50 border-gray-200";
}

export default function MilestoneDetail({ site }: Props) {
  const sorted = [...site.milestones].sort((a, b) => a.sort_order - b.sort_order);

  // Group by phase_type
  const phases: Record<string, Milestone[]> = {};
  for (const m of sorted) {
    const phase = m.phase_type || "Other";
    if (!phases[phase]) phases[phase] = [];
    phases[phase].push(m);
  }

  return (
    <div className="space-y-4">
      {Object.entries(phases).map(([phase, items]) => (
        <div key={phase}>
          <h4 className="text-xs font-bold text-gray-500 uppercase mb-2 tracking-wide">
            {phase}
          </h4>
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {items.map((m) => (
              <MilestoneCard key={m.key} milestone={m} />
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function MilestoneCard({ milestone: m }: { milestone: Milestone }) {
  const color = getStatusColor(m.status);

  return (
    <div
      className={`rounded-lg border p-3 ${statusBg(m.status)} transition-all hover:shadow-md`}
    >
      <div className="flex items-start justify-between mb-2">
        <div className="flex items-center gap-2">
          <div
            className="w-6 h-6 rounded-full flex items-center justify-center text-white text-xs font-bold flex-shrink-0"
            style={{ backgroundColor: color }}
          >
            {statusIcon(m.status)}
          </div>
          <span className="text-sm font-semibold text-gray-800">{m.name}</span>
        </div>
      </div>

      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">
        <div className="text-gray-500">Planned</div>
        <div className="text-gray-700 font-medium">
          {m.planned_start === m.planned_finish
            ? m.planned_start || "—"
            : `${m.planned_start || "—"} → ${m.planned_finish || "—"}`}
        </div>

        <div className="text-gray-500">Actual</div>
        <div className="text-gray-700 font-medium">{m.actual_finish || "—"}</div>

        <div className="text-gray-500">Duration</div>
        <div className="text-gray-700">{m.expected_days}d expected</div>

        {m.task_owner && (
          <>
            <div className="text-gray-500">Owner</div>
            <div className="text-gray-700">{m.task_owner}</div>
          </>
        )}

        {m.delay_days > 0 && (
          <>
            <div className="text-red-600 font-medium">Delay</div>
            <div className="text-red-700 font-bold">{m.delay_days} days</div>
          </>
        )}
      </div>

      <div className="mt-2 flex items-center gap-1.5">
        <span
          className="text-[10px] font-bold px-2 py-0.5 rounded-full text-white"
          style={{ backgroundColor: color }}
        >
          {m.status}
        </span>
        {m.preceding_milestones.length > 0 && (
          <span className="text-[10px] text-gray-400">← {m.preceding_milestones[0]}</span>
        )}
      </div>
    </div>
  );
}
