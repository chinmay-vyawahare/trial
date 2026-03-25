"use client";

import { useEffect, useState, useMemo } from "react";
import { PrerequisiteDefinition, UserExpectedDaysEntry, UserHistoryExpectedDaysEntry } from "@/lib/types";
import { getPrerequisites, getUserExpectedDays, setUserExpectedDays, deleteUserExpectedDays, getUserHistoryExpectedDays, resetSlaHistory } from "@/lib/api";

interface Props {
  userId: string;
}

export default function UserExpectedDays({ userId }: Props) {
  const [overrides, setOverrides] = useState<UserExpectedDaysEntry[]>([]);
  const [historyEntries, setHistoryEntries] = useState<UserHistoryExpectedDaysEntry[]>([]);
  const [allPrereqs, setAllPrereqs] = useState<PrerequisiteDefinition[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<string | null>(null);
  const [editingKey, setEditingKey] = useState<string | null>(null);
  const [editDays, setEditDays] = useState(0);
  const [resetting, setResetting] = useState(false);
  const [deleting, setDeleting] = useState<string | null>(null);

  const overrideMap = useMemo(() => {
    const map = new Map<string, number>();
    for (const o of overrides) map.set(o.milestone_key, o.expected_days);
    return map;
  }, [overrides]);

  const historyMap = useMemo(() => {
    const map = new Map<string, UserHistoryExpectedDaysEntry>();
    for (const e of historyEntries) map.set(e.milestone_key, e);
    return map;
  }, [historyEntries]);

  useEffect(() => {
    setLoading(true);
    getPrerequisites()
      .then(setAllPrereqs)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    if (userId) {
      loadOverrides();
      loadHistory();
    } else {
      setOverrides([]);
      setHistoryEntries([]);
    }
  }, [userId]);

  async function loadOverrides() {
    try {
      const data = await getUserExpectedDays(userId);
      setOverrides(data);
    } catch {
      setOverrides([]);
    }
  }

  async function loadHistory() {
    try {
      const data = await getUserHistoryExpectedDays(userId);
      setHistoryEntries(data);
    } catch {
      setHistoryEntries([]);
    }
  }

  function loadAll() {
    loadOverrides();
    loadHistory();
  }

  function startEdit(prereq: PrerequisiteDefinition) {
    setEditingKey(prereq.key);
    setEditDays(overrideMap.get(prereq.key) ?? prereq.expected_days);
  }

  async function handleSave(key: string) {
    if (!userId) return;
    setSaving(key);
    try {
      await setUserExpectedDays(userId, { milestone_key: key, expected_days: editDays });
      setEditingKey(null);
      await loadOverrides();
    } catch (e) {
      console.error("Failed to save:", e);
    } finally {
      setSaving(null);
    }
  }

  async function handleDelete(key: string) {
    if (!userId) return;
    if (!confirm(`Remove your override for "${key}"?`)) return;
    setDeleting(key);
    try {
      await deleteUserExpectedDays(userId, key);
      await loadOverrides();
    } catch (e) {
      console.error("Failed to delete:", e);
    } finally {
      setDeleting(null);
    }
  }

  async function handleResetHistory() {
    if (!userId) return;
    if (!confirm(`Reset all history SLA values for user "${userId}"?`)) return;
    setResetting(true);
    try {
      await resetSlaHistory(userId);
      setHistoryEntries([]);
    } catch (e) {
      console.error("Failed to reset:", e);
    } finally {
      setResetting(false);
    }
  }

  if (!userId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Enter a User ID in the top bar and click Apply to manage expected days.
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-full">
        <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
      </div>
    );
  }

  const dateFrom = historyEntries.length > 0 ? historyEntries[0].date_from : null;
  const dateTo = historyEntries.length > 0 ? historyEntries[0].date_to : null;

  return (
    <div className="h-full overflow-auto p-5">
      <div className="max-w-6xl mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold text-gray-800">User Expected Days</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              User: <span className="font-semibold text-blue-700">{userId}</span>
              {dateFrom && dateTo && (
                <>
                  {" — "}History computed from:{" "}
                  <span className="font-semibold text-purple-700">
                    {dateFrom.slice(0, 10)} → {dateTo.slice(0, 10)}
                  </span>
                </>
              )}
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={loadAll}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-gray-100 text-gray-600 hover:bg-gray-200 border border-gray-200"
            >
              Refresh
            </button>
            {historyEntries.length > 0 && (
              <button
                onClick={handleResetHistory}
                disabled={resetting}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-red-50 text-red-600 hover:bg-red-100 border border-red-200 disabled:opacity-50"
              >
                {resetting ? "Resetting..." : "Reset History SLA"}
              </button>
            )}
          </div>
        </div>

        <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">#</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Key</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Milestone Name</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Owner</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Phase</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Default Days</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-purple-600 uppercase bg-purple-50/50">History Days</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-emerald-600 uppercase bg-emerald-50/50">Your Days</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody>
                {allPrereqs.map((p) => {
                  const userDays = overrideMap.get(p.key);
                  const hasOverride = userDays !== undefined;
                  const historyEntry = historyMap.get(p.key);
                  const hasHistory = historyEntry !== undefined;
                  const isEditing = editingKey === p.key;

                  return (
                    <tr
                      key={p.key}
                      className={`border-b border-gray-50 transition-colors ${
                        hasOverride || hasHistory ? "bg-blue-50/30 hover:bg-blue-50" : "hover:bg-gray-50"
                      }`}
                    >
                      <td className="px-3 py-2 text-gray-400">{p.sort_order}</td>
                      <td className="px-3 py-2 font-mono text-blue-700 font-medium text-xs">{p.key}</td>
                      <td className="px-3 py-2 font-medium text-gray-800">{p.name}</td>
                      <td className="px-3 py-2 text-xs text-gray-500">{p.task_owner || "—"}</td>
                      <td className="px-3 py-2">
                        <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                          {p.phase_type || "—"}
                        </span>
                      </td>
                      <td className="px-3 py-2">
                        <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-blue-50 text-blue-700 border border-blue-200">
                          {p.expected_days}d
                        </span>
                      </td>
                      {/* History Days column */}
                      <td className="px-3 py-2 bg-purple-50/20">
                        {hasHistory ? (
                          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                            {historyEntry.history_expected_days}d
                          </span>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </td>
                      {/* User Override Days column */}
                      <td className="px-3 py-2 bg-emerald-50/20">
                        {isEditing ? (
                          <input
                            type="number"
                            value={editDays}
                            onChange={(e) => setEditDays(Number(e.target.value))}
                            onKeyDown={(e) => { if (e.key === "Enter") handleSave(p.key); if (e.key === "Escape") setEditingKey(null); }}
                            className="px-2 py-1 text-xs border border-blue-300 rounded w-20 focus:outline-none focus:ring-2 focus:ring-blue-400"
                            autoFocus
                          />
                        ) : hasOverride ? (
                          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-emerald-50 text-emerald-700 border border-emerald-200">
                            {userDays}d
                          </span>
                        ) : (
                          <span className="text-xs text-gray-300">—</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {isEditing ? (
                          <div className="flex gap-1">
                            <button
                              onClick={() => handleSave(p.key)}
                              disabled={saving === p.key}
                              className="px-2 py-1 text-[10px] font-medium rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                            >
                              {saving === p.key ? "..." : "Save"}
                            </button>
                            <button
                              onClick={() => setEditingKey(null)}
                              className="px-2 py-1 text-[10px] font-medium rounded bg-gray-200 text-gray-700 hover:bg-gray-300"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <div className="flex gap-1">
                            <button
                              onClick={() => startEdit(p)}
                              className="px-2 py-1 text-[10px] font-medium rounded bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200"
                            >
                              Edit
                            </button>
                            {hasOverride && (
                              <button
                                onClick={() => handleDelete(p.key)}
                                disabled={deleting === p.key}
                                className="px-2 py-1 text-[10px] font-medium rounded bg-red-50 text-red-600 hover:bg-red-100 border border-red-200 disabled:opacity-50"
                              >
                                {deleting === p.key ? "..." : "Delete"}
                              </button>
                            )}
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
