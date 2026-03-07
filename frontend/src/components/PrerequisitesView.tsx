"use client";

import { useEffect, useState } from "react";
import { PrerequisiteDefinition } from "@/lib/types";
import { getPrerequisites, getPrerequisiteFlowchart } from "@/lib/api";

export default function PrerequisitesView() {
  const [prerequisites, setPrerequisites] = useState<PrerequisiteDefinition[]>([]);
  const [mermaid, setMermaid] = useState("");
  const [loading, setLoading] = useState(true);
  const [viewMode, setViewMode] = useState<"table" | "flowchart">("table");

  useEffect(() => {
    setLoading(true);
    Promise.all([getPrerequisites(), getPrerequisiteFlowchart()])
      .then(([prereqs, chart]) => {
        setPrerequisites(prereqs);
        setMermaid(chart);
      })
      .catch((e) => console.error("Failed to load prerequisites:", e))
      .finally(() => setLoading(false));
  }, []);

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Toggle */}
      <div className="flex items-center gap-2 px-5 py-3 bg-white border-b border-gray-200">
        <button
          onClick={() => setViewMode("table")}
          className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
            viewMode === "table"
              ? "bg-blue-600 text-white"
              : "text-gray-500 hover:bg-gray-100"
          }`}
        >
          Table View
        </button>
        <button
          onClick={() => setViewMode("flowchart")}
          className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
            viewMode === "flowchart"
              ? "bg-blue-600 text-white"
              : "text-gray-500 hover:bg-gray-100"
          }`}
        >
          Flowchart
        </button>
        <span className="ml-auto text-xs text-gray-400">
          {prerequisites.length} milestones
        </span>
      </div>

      {viewMode === "table" ? (
        <div className="flex-1 overflow-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b sticky top-0">
              <tr>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase">#</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase">Key</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase">Name</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase">Expected Days</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase">History Days</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase">SLA Type</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase">Owner</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase">Phase</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase">Preceding</th>
                <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-500 uppercase">Following</th>
              </tr>
            </thead>
            <tbody>
              {prerequisites.map((p) => (
                <tr key={p.key} className="border-b border-gray-50 hover:bg-blue-50 transition-colors">
                  <td className="px-4 py-2 text-gray-400">{p.sort_order}</td>
                  <td className="px-4 py-2 font-mono text-blue-700 font-medium">{p.key}</td>
                  <td className="px-4 py-2 text-gray-800 font-medium">{p.name}</td>
                  <td className="px-4 py-2">
                    <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                      {p.expected_days}d
                    </span>
                  </td>
                  <td className="px-4 py-2">
                    {p.history_expected_days !== null ? (
                      <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                        {p.history_expected_days}d
                      </span>
                    ) : (
                      <span className="text-gray-300">—</span>
                    )}
                  </td>
                  <td className="px-4 py-2">
                    <span className={`text-xs font-medium ${p.sla_type === "history" ? "text-purple-600" : "text-gray-500"}`}>
                      {p.sla_type}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-gray-600 text-xs">{p.task_owner || "—"}</td>
                  <td className="px-4 py-2">
                    <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                      {p.phase_type || "—"}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-500 max-w-[180px] truncate">
                    {p.preceding_milestones.length > 0 ? p.preceding_milestones.join(", ") : "—"}
                  </td>
                  <td className="px-4 py-2 text-xs text-gray-500 max-w-[180px] truncate">
                    {p.following_milestones.length > 0 ? p.following_milestones.join(", ") : "—"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex-1 overflow-auto bg-white p-5">
          <div className="mb-3 flex items-center gap-3">
            <span className="text-xs text-gray-400">
              Copy the Mermaid markup below into{" "}
              <a href="https://mermaid.live" target="_blank" rel="noopener noreferrer" className="text-blue-500 underline">
                mermaid.live
              </a>{" "}
              to render the flowchart.
            </span>
            <button
              onClick={() => navigator.clipboard.writeText(mermaid)}
              className="px-3 py-1 text-xs font-medium rounded-lg border border-gray-200 text-gray-600 bg-white hover:bg-gray-50"
            >
              Copy to Clipboard
            </button>
          </div>
          <pre className="bg-gray-50 border border-gray-200 rounded-xl p-4 text-xs font-mono text-gray-700 overflow-auto whitespace-pre max-h-[calc(100vh-260px)]">
            {mermaid}
          </pre>
        </div>
      )}
    </div>
  );
}
