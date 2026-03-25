"use client";

import { useEffect, useState } from "react";
import {
  DashboardSlaSummary,
  SlaMilestone,
  ConstraintThreshold,
} from "@/lib/types";
import {
  getDashboardSlaSummary,
  getConstraints,
  getMilestoneConstraints,
  getOverallConstraints,
} from "@/lib/api";

export default function AnalyticsView() {
  const [slaSummary, setSlaSummary] = useState<DashboardSlaSummary | null>(null);
  const [constraints, setConstraints] = useState<ConstraintThreshold[]>([]);
  const [milestoneConstraints, setMilestoneConstraints] = useState<ConstraintThreshold[]>([]);
  const [overallConstraints, setOverallConstraints] = useState<ConstraintThreshold[]>([]);
  const [loading, setLoading] = useState(true);
  const [dateFrom, setDateFrom] = useState(() => {
    const d = new Date();
    d.setMonth(d.getMonth() - 6);
    return d.toISOString().slice(0, 10);
  });
  const [dateTo, setDateTo] = useState(() => new Date().toISOString().slice(0, 10));
  const [activeSection, setActiveSection] = useState<"sla" | "constraints">("sla");

  useEffect(() => {
    setLoading(true);
    Promise.all([
      getDashboardSlaSummary({ date_from: dateFrom, date_to: dateTo }),
      getConstraints(),
      getMilestoneConstraints(),
      getOverallConstraints(),
    ])
      .then(([sla, cons, mileCons, overCons]) => {
        setSlaSummary(sla);
        setConstraints(cons);
        setMilestoneConstraints(mileCons);
        setOverallConstraints(overCons);
      })
      .catch((e) => console.error("Failed to load analytics:", e))
      .finally(() => setLoading(false));
  }, [dateFrom, dateTo]);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Header */}
      <div className="flex items-center gap-3 px-5 py-3 bg-white border-b border-gray-200">
        <button
          onClick={() => setActiveSection("sla")}
          className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
            activeSection === "sla"
              ? "bg-blue-600 text-white"
              : "text-gray-500 hover:bg-gray-100"
          }`}
        >
          SLA History
        </button>
        <button
          onClick={() => setActiveSection("constraints")}
          className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
            activeSection === "constraints"
              ? "bg-blue-600 text-white"
              : "text-gray-500 hover:bg-gray-100"
          }`}
        >
          Constraints
        </button>

        <div className="ml-auto flex items-center gap-2">
          <label className="text-xs text-gray-400">From</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="px-2 py-1 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
          <label className="text-xs text-gray-400">To</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="px-2 py-1 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 focus:outline-none focus:ring-2 focus:ring-blue-400"
          />
        </div>
      </div>

      <div className="flex-1 overflow-auto p-5">
        {activeSection === "sla" ? (
          <SlaSection summary={slaSummary} />
        ) : (
          <ConstraintsSection
            constraints={constraints}
            milestoneConstraints={milestoneConstraints}
            overallConstraints={overallConstraints}
          />
        )}
      </div>
    </div>
  );
}

/* ── SLA History Section ────────────────────────────────────────────── */

function SlaSection({ summary }: { summary: DashboardSlaSummary | null }) {
  if (!summary) {
    return <p className="text-sm text-gray-400">No SLA data available for the selected range.</p>;
  }

  return (
    <div className="space-y-6">
      {/* Summary cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
        <StatCard label="Total Sites" value={summary.total_sites} color="bg-blue-600" />
        <StatCard label="On Track" value={summary.on_track_sites} color="bg-emerald-600" />
        <StatCard label="In Progress" value={summary.in_progress_sites} color="bg-amber-500" />
        <StatCard label="Critical" value={summary.critical_sites} color="bg-red-600" />
        <StatCard label="Blocked" value={summary.blocked_sites} color="bg-gray-500" />
      </div>

      <div className="bg-white rounded-xl shadow border border-gray-200 p-4">
        <div className="flex items-center justify-between mb-3">
          <h3 className="font-bold text-gray-800">SLA Milestones</h3>
          <span className="text-xs text-gray-400">
            {summary.date_from} - {summary.date_to} | Type: {summary.sla_type}
          </span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Milestone</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Default Days</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">History Days</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Sample Count</th>
              </tr>
            </thead>
            <tbody>
              {summary.sla_milestones.map((m: SlaMilestone) => (
                <tr key={m.milestone_key} className="border-b border-gray-50 hover:bg-blue-50 transition-colors">
                  <td className="px-3 py-2">
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-800">{m.milestone_name}</span>
                      <span className="font-mono text-xs text-gray-400">{m.milestone_key}</span>
                    </div>
                  </td>
                  <td className="px-3 py-2">
                    <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                      {m.default_expected_days}d
                    </span>
                  </td>
                  <td className="px-3 py-2">
                    {m.history_expected_days !== null ? (
                      <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                        {m.history_expected_days}d
                      </span>
                    ) : (
                      <span className="text-gray-300">--</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-gray-600">{m.sample_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function StatCard({ label, value, color }: { label: string; value: number; color: string }) {
  return (
    <div className={`${color} rounded-xl p-4 text-white shadow-lg`}>
      <div className="text-sm font-medium opacity-90">{label}</div>
      <div className="text-3xl font-bold mt-1">{value}</div>
    </div>
  );
}

/* ── Constraints Section ────────────────────────────────────────────── */

function ConstraintsSection({
  constraints,
  milestoneConstraints,
  overallConstraints,
}: {
  constraints: ConstraintThreshold[];
  milestoneConstraints: ConstraintThreshold[];
  overallConstraints: ConstraintThreshold[];
}) {
  return (
    <div className="space-y-6">
      <ConstraintTable title="All Constraints" items={constraints} />
      <ConstraintTable title="Milestone Constraints" items={milestoneConstraints} />
      <ConstraintTable title="Overall Constraints" items={overallConstraints} />
    </div>
  );
}

function ConstraintTable({ title, items }: { title: string; items: ConstraintThreshold[] }) {
  if (items.length === 0) {
    return (
      <div className="bg-white rounded-xl shadow border border-gray-200 p-4">
        <h3 className="font-bold text-gray-800 mb-2">{title}</h3>
        <p className="text-sm text-gray-400">No constraints configured.</p>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 p-4">
      <h3 className="font-bold text-gray-800 mb-3">{title}</h3>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3">
        {items.map((c) => (
          <div
            key={c.id}
            className="rounded-lg border border-gray-200 p-3 flex items-start gap-3"
          >
            <div
              className="w-4 h-4 rounded-full flex-shrink-0 mt-0.5"
              style={{ backgroundColor: c.color }}
            />
            <div className="min-w-0">
              <div className="text-sm font-semibold text-gray-800">{c.status_label}</div>
              <div className="text-xs text-gray-500">{c.name}</div>
              <div className="text-xs text-gray-400 mt-1">
                {c.constraint_type} | {c.min_pct}{c.max_pct !== null ? ` - ${c.max_pct}` : "+"}
              </div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
