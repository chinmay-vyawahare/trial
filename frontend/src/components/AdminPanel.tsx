"use client";

import { useEffect, useState, useMemo } from "react";
import {
  PrerequisiteDefinition,
  ConstraintThreshold,
  UserExpectedDaysEntry,
  ConstraintThresholdCreate,
  MilestoneDefinitionCreate,
  MilestoneColumnCreate,
} from "@/lib/types";
import {
  getPrerequisites,
  getStagingColumns,
  getConstraints,
  createConstraint,
  deleteConstraint,
  createPrerequisite,
  updatePrerequisite,
  adminGetSkippedPrerequisites,
  adminSkipPrerequisite,
  adminUnskipPrerequisite,
  adminUnskipAllPrerequisites,
  resetSlaHistory,
  getUserExpectedDays,
  setUserExpectedDays,
} from "@/lib/api";

type Section = "prerequisites" | "constraints" | "staging" | "sla" | "expected-days";

export default function AdminPanel() {
  const [section, setSection] = useState<Section>("prerequisites");

  const sections: { key: Section; label: string }[] = [
    { key: "prerequisites", label: "Prerequisites" },
    { key: "constraints", label: "Constraints" },
    { key: "expected-days", label: "Expected Days" },
    { key: "sla", label: "SLA History" },
    { key: "staging", label: "Staging Columns" },
  ];

  return (
    <div className="h-full flex flex-col overflow-hidden">
      {/* Section tabs */}
      <div className="flex items-center gap-1 px-5 py-3 bg-white border-b border-gray-200 flex-wrap">
        {sections.map((s) => (
          <button
            key={s.key}
            onClick={() => setSection(s.key)}
            className={`px-3 py-1.5 text-xs font-semibold rounded-lg transition-colors ${
              section === s.key
                ? "bg-blue-600 text-white"
                : "text-gray-500 hover:bg-gray-100"
            }`}
          >
            {s.label}
          </button>
        ))}
      </div>

      <div className="flex-1 overflow-auto p-5">
        {section === "prerequisites" && <PrerequisitesAdmin />}
        {section === "constraints" && <ConstraintsAdmin />}
{section === "expected-days" && <ExpectedDaysAdmin />}
        {section === "sla" && <SlaResetAdmin />}
        {section === "staging" && <StagingColumnsAdmin />}
      </div>
    </div>
  );
}

/* ── Prerequisites Admin ───────────────────────────────────────────── */

function PrerequisitesAdmin() {
  const [prerequisites, setPrerequisites] = useState<PrerequisiteDefinition[]>([]);
  const [stagingCols, setStagingCols] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [editId, setEditId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");
  const [editDays, setEditDays] = useState(0);
  const [editOwner, setEditOwner] = useState("");
  const [editPhase, setEditPhase] = useState("");
  const [saving, setSaving] = useState(false);
  const [showCreate, setShowCreate] = useState(false);
  const [createError, setCreateError] = useState("");
  const [skippedKeys, setSkippedKeys] = useState<Set<string>>(new Set());

  // Create form state
  const [newKey, setNewKey] = useState("");
  const [newName, setNewName] = useState("");
  const [newDays, setNewDays] = useState(1);
  const [newGapDays, setNewGapDays] = useState(1);
  const [newOwner, setNewOwner] = useState("");
  const [newPhase, setNewPhase] = useState("");
  const [newPreceding, setNewPreceding] = useState<string[]>([]);
  const [newFollowing, setNewFollowing] = useState<string[]>([]);
  const [newInsertAfter, setNewInsertAfter] = useState("");
  const [newColumns, setNewColumns] = useState<MilestoneColumnCreate[]>([
    { column_name: "", column_role: "actual", logic: null },
  ]);

  useEffect(() => {
    loadData();
  }, []);

  function loadData() {
    setLoading(true);
    Promise.all([getPrerequisites(), getStagingColumns(), adminGetSkippedPrerequisites()])
      .then(([prereqs, cols, skipped]) => {
        setPrerequisites(prereqs);
        setStagingCols(cols);
        setSkippedKeys(new Set(skipped.map((s) => s.key)));
      })
      .catch((e) => console.error("Failed to load prerequisites:", e))
      .finally(() => setLoading(false));
  }

  async function handleSkip(key: string) {
    try {
      await adminSkipPrerequisite(key);
      loadData();
    } catch (e) {
      console.error("Failed to skip:", e);
    }
  }

  async function handleUnskip(key: string) {
    try {
      await adminUnskipPrerequisite(key);
      loadData();
    } catch (e) {
      console.error("Failed to unskip:", e);
    }
  }

  async function handleUnskipAll() {
    try {
      await adminUnskipAllPrerequisites();
      loadData();
    } catch (e) {
      console.error("Failed to unskip all:", e);
    }
  }

  function startEdit(p: PrerequisiteDefinition) {
    setEditId(p.id);
    setEditName(p.name);
    setEditDays(p.expected_days);
    setEditOwner(p.task_owner || "");
    setEditPhase(p.phase_type || "");
  }

  async function handleSave() {
    if (editId === null) return;
    setSaving(true);
    try {
      await updatePrerequisite(editId, {
        name: editName,
        expected_days: editDays,
        task_owner: editOwner || null,
        phase_type: editPhase || null,
      });
      setEditId(null);
      loadData();
    } catch (e) {
      console.error("Failed to update prerequisite:", e);
    } finally {
      setSaving(false);
    }
  }

  function addColumn() {
    setNewColumns([...newColumns, { column_name: "", column_role: "actual", logic: null }]);
  }

  function removeColumn(idx: number) {
    setNewColumns(newColumns.filter((_, i) => i !== idx));
  }

  function updateColumn(idx: number, field: keyof MilestoneColumnCreate, value: string | null) {
    const updated = [...newColumns];
    updated[idx] = { ...updated[idx], [field]: value };
    setNewColumns(updated);
  }

  function toggleMultiSelect(list: string[], setList: (v: string[]) => void, key: string) {
    if (list.includes(key)) setList(list.filter((k) => k !== key));
    else setList([...list, key]);
  }

  async function handleCreate() {
    setCreateError("");
    if (!newKey.trim() || !newName.trim()) {
      setCreateError("Key and Name are required.");
      return;
    }
    if (newColumns.length === 0 || !newColumns[0].column_name) {
      setCreateError("At least one column mapping is required.");
      return;
    }
    setSaving(true);
    try {
      const body: MilestoneDefinitionCreate = {
        key: newKey.trim(),
        name: newName.trim(),
        expected_days: newDays,
        start_gap_days: newGapDays,
        task_owner: newOwner || null,
        phase_type: newPhase || null,
        preceding_milestone_keys: newPreceding.length > 0 ? newPreceding : undefined,
        following_milestone_keys: newFollowing.length > 0 ? newFollowing : undefined,
        insert_after_key: newInsertAfter || null,
        columns: newColumns.filter((c) => c.column_name),
      };
      await createPrerequisite(body);
      setShowCreate(false);
      resetCreateForm();
      loadData();
    } catch (e) {
      setCreateError(e instanceof Error ? e.message : "Failed to create prerequisite.");
    } finally {
      setSaving(false);
    }
  }

  function resetCreateForm() {
    setNewKey(""); setNewName(""); setNewDays(1); setNewGapDays(1);
    setNewOwner(""); setNewPhase(""); setNewPreceding([]);
    setNewFollowing([]); setNewInsertAfter("");
    setNewColumns([{ column_name: "", column_role: "actual", logic: null }]);
    setCreateError("");
  }

  const ownerOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of prerequisites) if (p.task_owner) set.add(p.task_owner);
    return [...set].sort();
  }, [prerequisites]);

  const phaseOptions = useMemo(() => {
    const set = new Set<string>();
    for (const p of prerequisites) if (p.phase_type) set.add(p.phase_type);
    return [...set].sort();
  }, [prerequisites]);

  if (loading) return <Spinner />;

  return (
    <div className="space-y-4">
      {/* Header with Add button */}
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-gray-800">
          Prerequisite Definitions
          {skippedKeys.size > 0 && (
            <span className="ml-2 text-xs font-normal text-orange-600">
              ({skippedKeys.size} skipped)
            </span>
          )}
        </h3>
        <div className="flex items-center gap-2">
          {skippedKeys.size > 0 && (
            <button onClick={handleUnskipAll}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-red-50 text-red-700 hover:bg-red-100 border border-red-200">
              Unskip All
            </button>
          )}
          <button onClick={() => setShowCreate(true)}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700">
            Add Prerequisite
          </button>
        </div>
      </div>

      {/* Modal popup */}
      {showCreate && (
        <div className="fixed inset-0 z-50 flex items-center justify-center">
          {/* Backdrop */}
          <div className="absolute inset-0 bg-black/40" onClick={() => { setShowCreate(false); resetCreateForm(); }} />

          {/* Modal */}
          <div className="relative bg-white rounded-2xl shadow-2xl border border-gray-200 w-full max-w-2xl max-h-[85vh] overflow-y-auto mx-4 p-6 space-y-5">
            <div className="flex items-center justify-between">
              <h4 className="text-base font-bold text-gray-800">Create New Prerequisite</h4>
              <button onClick={() => { setShowCreate(false); resetCreateForm(); }}
                className="w-7 h-7 rounded-full flex items-center justify-center text-gray-400 hover:bg-gray-100 hover:text-gray-600">
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {createError && (
              <div className="px-3 py-2 text-xs text-red-700 bg-red-50 border border-red-200 rounded-lg">{createError}</div>
            )}

            {/* Basic fields */}
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Key *</label>
                <input value={newKey} onChange={(e) => setNewKey(e.target.value)} placeholder="e.g. 9999"
                  className="w-full px-2.5 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Name *</label>
                <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Milestone name"
                  className="w-full px-2.5 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Expected Days</label>
                <input type="number" value={newDays} onChange={(e) => setNewDays(Number(e.target.value))}
                  className="w-full px-2.5 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Start Gap Days</label>
                <input type="number" value={newGapDays} onChange={(e) => setNewGapDays(Number(e.target.value))}
                  className="w-full px-2.5 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400" />
              </div>
              <div>
                <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Task Owner</label>
                <select value={newOwner} onChange={(e) => setNewOwner(e.target.value)}
                  className="w-full px-2.5 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400">
                  <option value="">Select owner...</option>
                  {ownerOptions.map((o) => (
                    <option key={o} value={o}>{o}</option>
                  ))}
                </select>
              </div>
              <div>
                <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Phase Type</label>
                <select value={newPhase} onChange={(e) => setNewPhase(e.target.value)}
                  className="w-full px-2.5 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400">
                  <option value="">Select phase...</option>
                  {phaseOptions.map((ph) => (
                    <option key={ph} value={ph}>{ph}</option>
                  ))}
                </select>
              </div>
              <div className="col-span-2">
                <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Insert After</label>
                <select value={newInsertAfter} onChange={(e) => setNewInsertAfter(e.target.value)}
                  className="w-full px-2.5 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400">
                  <option value="">Auto (after preceding)</option>
                  {prerequisites.map((p) => (
                    <option key={p.key} value={p.key}>{p.name} ({p.key})</option>
                  ))}
                </select>
              </div>
            </div>

            {/* Preceding / Following */}
            <div className="grid grid-cols-2 gap-4">
              <MultiSelectDropdown
                label="Preceding Milestones"
                options={prerequisites}
                selected={newPreceding}
                onToggle={(key) => toggleMultiSelect(newPreceding, setNewPreceding, key)}
              />
              <MultiSelectDropdown
                label="Following Milestones"
                options={prerequisites}
                selected={newFollowing}
                onToggle={(key) => toggleMultiSelect(newFollowing, setNewFollowing, key)}
              />
            </div>

            {/* Column mappings */}
            <div>
              <div className="flex items-center justify-between mb-2">
                <label className="text-[10px] font-bold text-gray-400 uppercase">Column Mappings *</label>
                <button onClick={addColumn}
                  className="px-2 py-0.5 text-[10px] font-medium rounded bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200">
                  + Add Column
                </button>
              </div>
              <div className="space-y-2">
                {newColumns.map((col, idx) => (
                  <div key={idx} className="flex items-center gap-2">
                    <select value={col.column_name} onChange={(e) => updateColumn(idx, "column_name", e.target.value)}
                      className="flex-1 px-2.5 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400">
                      <option value="">Select staging column...</option>
                      {stagingCols.map((c) => (
                        <option key={c} value={c}>{c}</option>
                      ))}
                    </select>
                    <select value={col.column_role} onChange={(e) => updateColumn(idx, "column_role", e.target.value)}
                      className="w-28 px-2.5 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400">
                      <option value="actual">actual</option>
                      <option value="text">text</option>
                    </select>
                    <input value={col.logic || ""} onChange={(e) => updateColumn(idx, "logic", e.target.value || null)}
                      placeholder="Logic (optional)" className="w-32 px-2.5 py-2 text-xs border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400" />
                    {newColumns.length > 1 && (
                      <button onClick={() => removeColumn(idx)}
                        className="px-2 py-1.5 text-[10px] font-medium rounded bg-red-50 text-red-600 hover:bg-red-100 border border-red-200">
                        X
                      </button>
                    )}
                  </div>
                ))}
              </div>
              <p className="text-[10px] text-gray-400 mt-1">Planned start & planned finish are calculated automatically.</p>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-3 pt-3 border-t border-gray-100">
              <button onClick={() => { setShowCreate(false); resetCreateForm(); }}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-gray-100 text-gray-600 hover:bg-gray-200">
                Cancel
              </button>
              <button onClick={handleCreate} disabled={saving}
                className="px-5 py-2 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50">
                {saving ? "Creating..." : "Create Prerequisite"}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Existing prerequisites table */}
      <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100">
          <p className="text-xs text-gray-400">Click Edit to modify a prerequisite inline. {prerequisites.length} milestones total.</p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">#</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Key</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Name</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Expected Days</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">History Days</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Owner</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Phase</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Preceding</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Last Updated</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Actions</th>
              </tr>
            </thead>
            <tbody>
              {prerequisites.map((p) => {
                const isSkipped = skippedKeys.has(p.key);
                return (
                <tr key={p.id} className={`border-b border-gray-50 transition-colors ${
                  isSkipped ? "bg-orange-50/50 hover:bg-orange-50" : "hover:bg-blue-50"
                }`}>
                  <td className="px-3 py-2 text-gray-400">{p.sort_order}</td>
                  <td className="px-3 py-2 font-mono text-blue-700 font-medium">{p.key}</td>
                  <td className="px-3 py-2">
                    {editId === p.id ? (
                      <input value={editName} onChange={(e) => setEditName(e.target.value)}
                        className="px-2 py-1 text-xs border border-gray-300 rounded w-full" />
                    ) : (
                      <span className={`font-medium ${isSkipped ? "text-gray-400 line-through" : "text-gray-800"}`}>{p.name}</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {editId === p.id ? (
                      <input type="number" value={editDays} onChange={(e) => setEditDays(Number(e.target.value))}
                        className="px-2 py-1 text-xs border border-gray-300 rounded w-20" />
                    ) : (
                      <span className={`px-2 py-0.5 text-xs font-semibold rounded-full ${isSkipped ? "bg-gray-100 text-gray-400" : "bg-blue-50 text-blue-700 border border-blue-200"}`}>
                        {p.expected_days}d
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {p.history_expected_days !== null ? (
                      <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                        {p.history_expected_days}d
                      </span>
                    ) : (
                      <span className="text-gray-400 text-xs">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {editId === p.id ? (
                      <select value={editOwner} onChange={(e) => setEditOwner(e.target.value)}
                        className="px-2 py-1 text-xs border border-gray-300 rounded w-full">
                        <option value="">Select owner...</option>
                        {ownerOptions.map((o) => (
                          <option key={o} value={o}>{o}</option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-gray-600 text-xs">{p.task_owner || "—"}</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {editId === p.id ? (
                      <select value={editPhase} onChange={(e) => setEditPhase(e.target.value)}
                        className="px-2 py-1 text-xs border border-gray-300 rounded w-full">
                        <option value="">Select phase...</option>
                        {phaseOptions.map((ph) => (
                          <option key={ph} value={ph}>{ph}</option>
                        ))}
                      </select>
                    ) : (
                      <span className="text-xs text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded">
                        {p.phase_type || "—"}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-500 max-w-[160px] truncate">
                    {p.preceding_milestones.length > 0 ? p.preceding_milestones.join(", ") : "—"}
                  </td>
                  <td className="px-3 py-2 text-xs text-gray-500">
                    {p.updated_at ? new Date(p.updated_at).toLocaleDateString() : "—"}
                  </td>
                  <td className="px-3 py-2">
                    {editId === p.id ? (
                      <div className="flex gap-1">
                        <button onClick={handleSave} disabled={saving}
                          className="px-2 py-1 text-[10px] font-medium rounded bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50">
                          Save
                        </button>
                        <button onClick={() => setEditId(null)}
                          className="px-2 py-1 text-[10px] font-medium rounded bg-gray-200 text-gray-700 hover:bg-gray-300">
                          Cancel
                        </button>
                      </div>
                    ) : (
                      <div className="flex gap-1">
                        <button onClick={() => startEdit(p)}
                          className="px-2 py-1 text-[10px] font-medium rounded bg-blue-50 text-blue-700 hover:bg-blue-100 border border-blue-200">
                          Edit
                        </button>
                        {isSkipped ? (
                          <button onClick={() => handleUnskip(p.key)}
                            className="px-2 py-1 text-[10px] font-medium rounded bg-emerald-50 text-emerald-700 hover:bg-emerald-100 border border-emerald-200">
                            Unskip
                          </button>
                        ) : (
                          <button onClick={() => handleSkip(p.key)}
                            className="px-2 py-1 text-[10px] font-medium rounded bg-orange-50 text-orange-700 hover:bg-orange-100 border border-orange-200">
                            Skip
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
  );
}

/* ── Constraints Admin ─────────────────────────────────────────────── */

function ConstraintsAdmin() {
  const [constraints, setConstraints] = useState<ConstraintThreshold[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [form, setForm] = useState<ConstraintThresholdCreate>({
    constraint_type: "milestone",
    name: "",
    status_label: "",
    color: "#22c55e",
    min_pct: 0,
    max_pct: null,
    sort_order: 0,
  });

  useEffect(() => { loadData(); }, []);

  function loadData() {
    setLoading(true);
    getConstraints()
      .then(setConstraints)
      .catch((e) => console.error("Failed:", e))
      .finally(() => setLoading(false));
  }

  async function handleCreate() {
    try {
      await createConstraint(form);
      setShowCreate(false);
      setForm({ constraint_type: "milestone", name: "", status_label: "", color: "#22c55e", min_pct: 0, max_pct: null, sort_order: 0 });
      loadData();
    } catch (e) {
      console.error("Failed to create:", e);
    }
  }

  async function handleDelete(id: number) {
    try {
      await deleteConstraint(id);
      loadData();
    } catch (e) {
      console.error("Failed to delete:", e);
    }
  }

  if (loading) return <Spinner />;

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-bold text-gray-800">Constraint Thresholds</h3>
        <button onClick={() => setShowCreate(!showCreate)}
          className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700">
          {showCreate ? "Cancel" : "Add Constraint"}
        </button>
      </div>

      {showCreate && (
        <div className="bg-white rounded-xl shadow border border-gray-200 p-4 space-y-3">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <div>
              <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Type</label>
              <select value={form.constraint_type} onChange={(e) => setForm({ ...form, constraint_type: e.target.value })}
                className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-lg">
                <option value="milestone">Milestone</option>
                <option value="overall">Overall</option>
              </select>
            </div>
            <div>
              <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Name</label>
              <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-lg" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Status Label</label>
              <input value={form.status_label} onChange={(e) => setForm({ ...form, status_label: e.target.value })}
                className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-lg" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Color</label>
              <input type="color" value={form.color} onChange={(e) => setForm({ ...form, color: e.target.value })}
                className="w-full h-8 rounded-lg border border-gray-200 cursor-pointer" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Min %</label>
              <input type="number" value={form.min_pct} onChange={(e) => setForm({ ...form, min_pct: Number(e.target.value) })}
                className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-lg" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Max %</label>
              <input type="number" value={form.max_pct ?? ""} onChange={(e) => setForm({ ...form, max_pct: e.target.value ? Number(e.target.value) : null })}
                placeholder="null = 100"
                className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-lg" />
            </div>
            <div>
              <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Sort Order</label>
              <input type="number" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: Number(e.target.value) })}
                className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-lg" />
            </div>
            <div className="flex items-end">
              <button onClick={handleCreate}
                className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600 text-white hover:bg-emerald-700">
                Create
              </button>
            </div>
          </div>
        </div>
      )}

      <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
        <table className="w-full text-sm">
          <thead className="bg-gray-50 border-b">
            <tr>
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Color</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Type</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Name</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Label</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Range</th>
              <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Actions</th>
            </tr>
          </thead>
          <tbody>
            {constraints.map((c) => (
              <tr key={c.id} className="border-b border-gray-50 hover:bg-blue-50 transition-colors">
                <td className="px-3 py-2">
                  <div className="w-5 h-5 rounded-full" style={{ backgroundColor: c.color }} />
                </td>
                <td className="px-3 py-2 text-xs text-gray-600">{c.constraint_type}</td>
                <td className="px-3 py-2 font-medium text-gray-800">{c.name}</td>
                <td className="px-3 py-2 text-gray-600">{c.status_label}</td>
                <td className="px-3 py-2 text-xs text-gray-500">{c.min_pct}%{c.max_pct !== null ? ` - ${c.max_pct}%` : "+"}</td>
                <td className="px-3 py-2">
                  <button onClick={() => handleDelete(c.id)}
                    className="px-2 py-1 text-[10px] font-medium rounded bg-red-50 text-red-700 hover:bg-red-100 border border-red-200">
                    Delete
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

/* ── Expected Days Override ────────────────────────────────────────── */

function ExpectedDaysAdmin() {
  const [userId, setUserId] = useState("default_user");
  const [entries, setEntries] = useState<UserExpectedDaysEntry[]>([]);
  const [allPrereqs, setAllPrereqs] = useState<PrerequisiteDefinition[]>([]);
  const [loading, setLoading] = useState(false);
  const [milestoneKey, setMilestoneKey] = useState("");
  const [days, setDays] = useState(0);
  const [msg, setMsg] = useState("");

  useEffect(() => {
    getPrerequisites().then(setAllPrereqs).catch(() => {});
  }, []);

  async function handleLoad() {
    setLoading(true);
    try {
      const data = await getUserExpectedDays(userId);
      setEntries(data);
      setMsg("");
    } catch {
      setEntries([]);
      setMsg("No overrides found for this user.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSet() {
    if (!milestoneKey) return;
    try {
      await setUserExpectedDays(userId, { milestone_key: milestoneKey, expected_days: days });
      setMsg("Saved!");
      handleLoad();
    } catch (e) {
      console.error("Failed:", e);
      setMsg("Failed to save.");
    }
  }

  return (
    <div className="space-y-4">
      <div className="bg-white rounded-xl shadow border border-gray-200 p-4">
        <h3 className="font-bold text-gray-800 mb-3">User Expected Days Overrides</h3>
        <div className="flex items-end gap-3 mb-4">
          <div>
            <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">User ID</label>
            <input value={userId} onChange={(e) => setUserId(e.target.value)}
              className="px-2 py-1.5 text-xs border border-gray-200 rounded-lg w-48" />
          </div>
          <button onClick={handleLoad}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700">
            Load
          </button>
        </div>

        <div className="flex items-end gap-3 mb-4">
          <div className="flex-1">
            <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Milestone</label>
            <select value={milestoneKey} onChange={(e) => setMilestoneKey(e.target.value)}
              className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded-lg">
              <option value="">Select milestone...</option>
              {allPrereqs.map((p) => (
                <option key={p.key} value={p.key}>{p.name} ({p.key})</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">Days</label>
            <input type="number" value={days} onChange={(e) => setDays(Number(e.target.value))}
              className="px-2 py-1.5 text-xs border border-gray-200 rounded-lg w-20" />
          </div>
          <button onClick={handleSet} disabled={!milestoneKey}
            className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600 text-white hover:bg-emerald-700 disabled:opacity-50">
            Set
          </button>
        </div>

        {msg && <p className="text-xs text-gray-500 mb-3">{msg}</p>}

        {loading ? <Spinner /> : entries.length > 0 && (
          <table className="w-full text-sm">
            <thead className="bg-gray-50 border-b">
              <tr>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Milestone Key</th>
                <th className="px-3 py-2 text-left text-xs font-semibold text-gray-500 uppercase">Expected Days</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((e) => (
                <tr key={e.id} className="border-b border-gray-50">
                  <td className="px-3 py-2 font-mono text-blue-700">{e.milestone_key}</td>
                  <td className="px-3 py-2">
                    <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-purple-50 text-purple-700 border border-purple-200">
                      {e.expected_days}d
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

/* ── SLA History Reset ─────────────────────────────────────────────── */

function SlaResetAdmin() {
  const [msg, setMsg] = useState("");
  const [resetting, setResetting] = useState(false);

  async function handleReset() {
    setResetting(true);
    try {
      const res = await resetSlaHistory();
      setMsg(res.detail);
    } catch (e) {
      setMsg(`Failed: ${e instanceof Error ? e.message : "unknown error"}`);
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 p-4">
      <h3 className="font-bold text-gray-800 mb-2">Reset SLA History</h3>
      <p className="text-xs text-gray-500 mb-4">
        Clear all history_expected_days from milestone definitions, reverting to default expected_days values.
      </p>
      <button onClick={handleReset} disabled={resetting}
        className="px-4 py-1.5 text-xs font-semibold rounded-lg bg-red-600 text-white hover:bg-red-700 disabled:opacity-50">
        {resetting ? "Resetting..." : "Reset to Default SLA"}
      </button>
      {msg && <p className="text-xs text-gray-500 mt-3">{msg}</p>}
    </div>
  );
}

/* ── Staging Columns ───────────────────────────────────────────────── */

function StagingColumnsAdmin() {
  const [columns, setColumns] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    getStagingColumns()
      .then(setColumns)
      .catch((e) => console.error("Failed:", e))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spinner />;

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 p-4">
      <h3 className="font-bold text-gray-800 mb-3">Staging Table Columns ({columns.length})</h3>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
        {columns.map((col) => (
          <div key={col} className="px-3 py-2 rounded-lg bg-gray-50 border border-gray-200 text-xs font-mono text-gray-700">
            {col}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ── Multi-Select Dropdown ──────────────────────────────────────────── */

function MultiSelectDropdown({
  label,
  options,
  selected,
  onToggle,
}: {
  label: string;
  options: PrerequisiteDefinition[];
  selected: string[];
  onToggle: (key: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [search, setSearch] = useState("");

  const filtered = search
    ? options.filter(
        (p) =>
          p.name.toLowerCase().includes(search.toLowerCase()) ||
          p.key.toLowerCase().includes(search.toLowerCase())
      )
    : options;

  return (
    <div className="relative">
      <label className="text-[10px] font-bold text-gray-400 uppercase block mb-1">
        {label} ({selected.length} selected)
      </label>

      {/* Trigger */}
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full px-2.5 py-2 text-xs border border-gray-200 rounded-lg bg-white text-left flex items-center justify-between focus:outline-none focus:ring-2 focus:ring-blue-400"
      >
        <span className="text-gray-600 truncate">
          {selected.length === 0
            ? "Select milestones..."
            : `${selected.length} selected`}
        </span>
        <svg
          className={`w-3.5 h-3.5 text-gray-400 transition-transform ${open ? "rotate-180" : ""}`}
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
        </svg>
      </button>

      {/* Selected tags */}
      {selected.length > 0 && (
        <div className="flex flex-wrap gap-1 mt-1.5">
          {selected.map((key) => {
            const p = options.find((o) => o.key === key);
            return (
              <span
                key={key}
                className="inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-medium rounded bg-blue-50 text-blue-700 border border-blue-200"
              >
                {p?.name || key}
                <button
                  type="button"
                  onClick={(e) => { e.stopPropagation(); onToggle(key); }}
                  className="text-blue-400 hover:text-blue-600"
                >
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                  </svg>
                </button>
              </span>
            );
          })}
        </div>
      )}

      {/* Dropdown */}
      {open && (
        <div className="absolute z-20 mt-1 w-full bg-white border border-gray-200 rounded-lg shadow-lg">
          <div className="p-1.5 border-b border-gray-100">
            <input
              type="text"
              placeholder="Search..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full px-2 py-1.5 text-xs border border-gray-200 rounded focus:outline-none focus:ring-2 focus:ring-blue-400"
              autoFocus
            />
          </div>
          <div className="max-h-48 overflow-y-auto p-1">
            {filtered.length === 0 ? (
              <p className="text-xs text-gray-400 px-2 py-2">No milestones found.</p>
            ) : (
              filtered.map((p) => (
                <label
                  key={p.key}
                  className="flex items-center gap-2 text-xs text-gray-700 cursor-pointer hover:bg-blue-50 px-2 py-1.5 rounded"
                >
                  <input
                    type="checkbox"
                    checked={selected.includes(p.key)}
                    onChange={() => onToggle(p.key)}
                    className="rounded border-gray-300"
                  />
                  <span className="flex-1">{p.name}</span>
                  <span className="text-gray-400 text-[10px]">{p.key}</span>
                </label>
              ))
            )}
          </div>
          <div className="p-1.5 border-t border-gray-100">
            <button
              type="button"
              onClick={() => { setOpen(false); setSearch(""); }}
              className="w-full px-2 py-1 text-[10px] font-medium rounded bg-gray-100 text-gray-600 hover:bg-gray-200"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Shared ────────────────────────────────────────────────────────── */

function Spinner() {
  return (
    <div className="flex items-center justify-center h-32">
      <div className="animate-spin w-8 h-8 border-3 border-blue-500 border-t-transparent rounded-full" />
    </div>
  );
}
