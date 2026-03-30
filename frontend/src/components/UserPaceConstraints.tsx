"use client";

import { useEffect, useState } from "react";
import { PaceConstraintEntry } from "@/lib/types";
import {
  getPaceConstraints,
  createPaceConstraint,
  updatePaceConstraint,
  deletePaceConstraint,
} from "@/lib/api";

interface Props {
  userId: string;
  onConstraintChange?: () => void;
}

export default function UserPaceConstraints({ userId, onConstraintChange }: Props) {
  const [entries, setEntries] = useState<PaceConstraintEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [saving, setSaving] = useState(false);

  // Create form
  const [newStartDate, setNewStartDate] = useState("");
  const [newEndDate, setNewEndDate] = useState("");
  const [newMarket, setNewMarket] = useState("");
  const [newArea, setNewArea] = useState("");
  const [newRegion, setNewRegion] = useState("");
  const [newMaxSites, setNewMaxSites] = useState(5);

  // Edit form
  const [editStartDate, setEditStartDate] = useState("");
  const [editEndDate, setEditEndDate] = useState("");
  const [editMarket, setEditMarket] = useState("");
  const [editArea, setEditArea] = useState("");
  const [editRegion, setEditRegion] = useState("");
  const [editMaxSites, setEditMaxSites] = useState(5);

  const load = async () => {
    setLoading(true);
    try {
      setEntries(await getPaceConstraints(userId));
    } catch {
      setEntries([]);
    }
    setLoading(false);
  };

  useEffect(() => {
    if (userId) load();
    else setEntries([]);
  }, [userId]);

  const handleCreate = async () => {
    setSaving(true);
    try {
      await createPaceConstraint({
        user_id: userId,
        start_date: newStartDate || null,
        end_date: newEndDate || null,
        market: newMarket.trim() || null,
        area: newArea.trim() || null,
        region: newRegion.trim() || null,
        max_sites: newMaxSites,
      });
      setShowCreate(false);
      setNewStartDate("");
      setNewEndDate("");
      setNewMarket("");
      setNewArea("");
      setNewRegion("");
      setNewMaxSites(5);
      await load();
      onConstraintChange?.();
    } catch {
      /* ignore */
    }
    setSaving(false);
  };

  const startEdit = (e: PaceConstraintEntry) => {
    setEditId(e.id);
    setEditStartDate(e.start_date ? e.start_date.slice(0, 10) : "");
    setEditEndDate(e.end_date ? e.end_date.slice(0, 10) : "");
    setEditMarket(e.market || "");
    setEditArea(e.area || "");
    setEditRegion(e.region || "");
    setEditMaxSites(e.max_sites);
  };

  const handleUpdate = async (id: number) => {
    setSaving(true);
    try {
      await updatePaceConstraint(id, userId, {
        start_date: editStartDate || undefined,
        end_date: editEndDate || undefined,
        market: editMarket.trim() || null,
        area: editArea.trim() || null,
        region: editRegion.trim() || null,
        max_sites: editMaxSites,
      });
      setEditId(null);
      await load();
      onConstraintChange?.();
    } catch {
      /* ignore */
    }
    setSaving(false);
  };

  const handleDelete = async (id: number) => {
    if (!confirm("Delete this pace constraint?")) return;
    try {
      await deletePaceConstraint(id, userId);
      await load();
      onConstraintChange?.();
    } catch {
      /* ignore */
    }
  };

  if (!userId) {
    return (
      <div className="flex items-center justify-center h-full text-gray-400 text-sm">
        Enter a User ID in the top bar and click Apply to manage pace constraints.
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

  return (
    <div className="h-full overflow-auto p-5">
      <div className="max-w-5xl mx-auto space-y-4">
        <div className="flex items-center justify-between">
          <div>
            <h3 className="font-bold text-gray-800">Pace Constraints</h3>
            <p className="text-xs text-gray-400 mt-0.5">
              User: <span className="font-semibold text-blue-700">{userId}</span>
              {" — "}Define date ranges and max sites per market/area/region. Sites nearest to start date get priority; excess are excluded.
            </p>
          </div>
          <div className="flex gap-2">
            <button
              onClick={load}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-gray-100 text-gray-600 hover:bg-gray-200 border border-gray-200"
            >
              Refresh
            </button>
            <button
              onClick={() => setShowCreate(!showCreate)}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700"
            >
              {showCreate ? "Cancel" : "+ Add Constraint"}
            </button>
          </div>
        </div>

        {/* Create form */}
        {showCreate && (
          <div className="bg-blue-50 rounded-xl border border-blue-200 p-4 space-y-3">
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-gray-500 block mb-1">Start Date</label>
                <input
                  type="date"
                  value={newStartDate}
                  onChange={(e) => setNewStartDate(e.target.value)}
                  className="w-full border rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">End Date</label>
                <input
                  type="date"
                  value={newEndDate}
                  onChange={(e) => setNewEndDate(e.target.value)}
                  className="w-full border rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Max Sites</label>
                <input
                  type="number"
                  value={newMaxSites}
                  onChange={(e) => setNewMaxSites(Number(e.target.value))}
                  className="w-full border rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                  min={1}
                />
              </div>
            </div>
            <div className="grid grid-cols-3 gap-3">
              <div>
                <label className="text-xs text-gray-500 block mb-1">Market</label>
                <input
                  value={newMarket}
                  onChange={(e) => setNewMarket(e.target.value)}
                  className="w-full border rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                  placeholder="Optional"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Area</label>
                <input
                  value={newArea}
                  onChange={(e) => setNewArea(e.target.value)}
                  className="w-full border rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                  placeholder="Optional"
                />
              </div>
              <div>
                <label className="text-xs text-gray-500 block mb-1">Region</label>
                <input
                  value={newRegion}
                  onChange={(e) => setNewRegion(e.target.value)}
                  className="w-full border rounded-lg px-2.5 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-blue-400"
                  placeholder="Optional"
                />
              </div>
            </div>
            <p className="text-xs text-gray-400">All fields are optional. If no dates are set, the constraint applies to the current week.</p>
            <button
              onClick={handleCreate}
              disabled={saving}
              className="px-4 py-1.5 text-xs font-semibold bg-emerald-600 text-white rounded-lg hover:bg-emerald-700 disabled:opacity-50"
            >
              {saving ? "Saving..." : "Create"}
            </button>
          </div>
        )}

        {/* Table */}
        <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-gray-50 border-b">
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Start Date</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">End Date</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Market</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Area</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Region</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Max Sites</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Actions</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => {
                  const isEditing = editId === e.id;

                  return (
                    <tr
                      key={e.id}
                      className="border-b border-gray-50 hover:bg-blue-50 transition-colors"
                    >
                      <td className="px-3 py-2">
                        {isEditing ? (
                          <input type="date" value={editStartDate} onChange={(ev) => setEditStartDate(ev.target.value)} className="border rounded px-2 py-1 text-xs w-32 focus:outline-none focus:ring-2 focus:ring-blue-400" />
                        ) : (
                          <span className="text-xs font-medium text-gray-700">{e.start_date ? new Date(e.start_date).toLocaleDateString() : "—"}</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {isEditing ? (
                          <input type="date" value={editEndDate} onChange={(ev) => setEditEndDate(ev.target.value)} className="border rounded px-2 py-1 text-xs w-32 focus:outline-none focus:ring-2 focus:ring-blue-400" />
                        ) : (
                          <span className="text-xs font-medium text-gray-700">{e.end_date ? new Date(e.end_date).toLocaleDateString() : "—"}</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {isEditing ? (
                          <input value={editMarket} onChange={(ev) => setEditMarket(ev.target.value)} className="border rounded px-2 py-1 text-xs w-24 focus:outline-none focus:ring-2 focus:ring-blue-400" placeholder="Optional" />
                        ) : (
                          <span className="text-xs text-gray-600">{e.market || "—"}</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {isEditing ? (
                          <input value={editArea} onChange={(ev) => setEditArea(ev.target.value)} className="border rounded px-2 py-1 text-xs w-24 focus:outline-none focus:ring-2 focus:ring-blue-400" placeholder="Optional" />
                        ) : (
                          <span className="text-xs text-gray-600">{e.area || "—"}</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {isEditing ? (
                          <input value={editRegion} onChange={(ev) => setEditRegion(ev.target.value)} className="border rounded px-2 py-1 text-xs w-24 focus:outline-none focus:ring-2 focus:ring-blue-400" placeholder="Optional" />
                        ) : (
                          <span className="text-xs text-gray-600">{e.region || "—"}</span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {isEditing ? (
                          <input type="number" value={editMaxSites} onChange={(ev) => setEditMaxSites(Number(ev.target.value))} className="border rounded px-2 py-1 text-xs w-16 focus:outline-none focus:ring-2 focus:ring-blue-400" min={1} />
                        ) : (
                          <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                            {e.max_sites}
                          </span>
                        )}
                      </td>
                      <td className="px-3 py-2">
                        {isEditing ? (
                          <div className="flex gap-1">
                            <button
                              onClick={() => handleUpdate(e.id)}
                              disabled={saving}
                              className="px-2 py-1 text-[10px] font-medium rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50"
                            >
                              {saving ? "..." : "Save"}
                            </button>
                            <button
                              onClick={() => setEditId(null)}
                              className="px-2 py-1 text-[10px] font-medium rounded bg-gray-200 text-gray-700 hover:bg-gray-300"
                            >
                              Cancel
                            </button>
                          </div>
                        ) : (
                          <div className="flex gap-1">
                            <button
                              onClick={() => startEdit(e)}
                              className="px-2 py-1 text-[10px] font-medium rounded bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200"
                            >
                              Edit
                            </button>
                            <button
                              onClick={() => handleDelete(e.id)}
                              className="px-2 py-1 text-[10px] font-medium rounded bg-red-50 text-red-700 hover:bg-red-100 border border-red-200"
                            >
                              Delete
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
                {entries.length === 0 && (
                  <tr>
                    <td colSpan={7} className="px-3 py-8 text-center text-gray-400 text-xs">
                      No pace constraints yet. Click &quot;+ Add Constraint&quot; to create one.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </div>
    </div>
  );
}
