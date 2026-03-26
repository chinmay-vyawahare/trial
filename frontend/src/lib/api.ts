import type {
  FilterOptions,
  GanttResponse,
  DashboardSummary,
  DashboardSlaSummary,
  ConstraintThreshold,
  ConstraintThresholdCreate,
  ConstraintThresholdUpdate,
  PrerequisiteDefinition,
  MilestoneDefinitionCreate,
  MilestoneDefinitionUpdate,
  SkippedPrerequisite,
  UserExpectedDaysEntry,
  GateCheckConfig,
  ChatResponse,
  ChatHistoryUser,
  ChatThreadSummary,
  ChatThread,
  UserFilter,
  SlaHistoryGanttResponse,
  GcCapacityEntry,
  PaceConstraintEntry,
  PaceConstraintCreate,
  PaceConstraintUpdate,
  PendingMilestonesResponse,
  PendingByMilestoneResponse,
  DrilldownResponse,
  UserHistoryExpectedDaysEntry,
  CxForecastSummaryResponse,
  CxActualSummaryResponse,
  SiteGantt,
  WeeklyStatusResponse,
} from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** Append a multi-value query param (e.g. region=A&region=B) or single value. */
function appendMulti(sp: URLSearchParams, key: string, values: string[] | string | undefined) {
  if (!values) return;
  if (Array.isArray(values)) {
    for (const v of values) {
      if (v) sp.append(key, v);
    }
  } else if (values) {
    sp.append(key, values);
  }
}

async function fetchAPI<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { cache: "no-store", ...init });
  if (!res.ok) {
    let detail = `API error: ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch { /* ignore parse errors */ }
    throw new Error(detail);
  }
  return res.json();
}

/* ── Filters (each returns string[]) ─────────────────────────────── */

export async function getFilterRegions(): Promise<string[]> {
  return fetchAPI<string[]>("/api/v1/schedular/filters/regions");
}

export async function getFilterMarkets(): Promise<string[]> {
  return fetchAPI<string[]>("/api/v1/schedular/filters/markets");
}

export async function getFilterAreas(): Promise<string[]> {
  return fetchAPI<string[]>("/api/v1/schedular/filters/areas");
}

export async function getFilterSites(): Promise<string[]> {
  return fetchAPI<string[]>("/api/v1/schedular/filters/sites");
}

export async function getFilterVendors(): Promise<string[]> {
  return fetchAPI<string[]>("/api/v1/schedular/filters/vendors");
}

export async function getAllFilters(): Promise<FilterOptions> {
  const [regions, markets, areas, site_ids, vendors, plan_types, dev_initiatives] = await Promise.all([
    getFilterRegions(),
    getFilterMarkets(),
    getFilterAreas(),
    getFilterSites(),
    getFilterVendors(),
    getGateCheckPlanTypes().catch(() => [] as string[]),
    getGateCheckDevInitiatives().catch(() => [] as string[]),
  ]);
  return { regions, markets, areas, site_ids, vendors, plan_types, dev_initiatives };
}

/* ── Gantt Charts ─────────────────────────────────────────────────── */

export async function getGanttCharts(filters?: {
  region?: string[];
  market?: string[];
  site_id?: string;
  vendor?: string;
  area?: string[];
  user_id?: string;
  limit?: number;
  offset?: number;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  status?: string;
}): Promise<GanttResponse> {
  const params = new URLSearchParams();
  appendMulti(params, "region", filters?.region);
  appendMulti(params, "market", filters?.market);
  if (filters?.site_id) params.set("site_id", filters.site_id);
  if (filters?.vendor) params.set("vendor", filters.vendor);
  appendMulti(params, "area", filters?.area);
  if (filters?.user_id) params.set("user_id", filters.user_id);
  if (filters?.limit) params.set("limit", String(filters.limit));
  if (filters?.offset) params.set("offset", String(filters.offset));
  if (filters?.consider_vendor_capacity) params.set("consider_vendor_capacity", "true");
  if (filters?.pace_constraint_flag) params.set("pace_constraint_flag", "true");
  if (filters?.status) params.set("status", filters.status);
  const qs = params.toString();
  return fetchAPI<GanttResponse>(`/api/v1/schedular/gantt-charts${qs ? `?${qs}` : ""}`);
}

/* ── Dashboard ────────────────────────────────────────────────────── */

export async function getDashboardSummary(filters?: {
  region?: string[];
  market?: string[];
  area?: string[];
  site_id?: string;
  vendor?: string;
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  status?: string;
}): Promise<DashboardSummary> {
  const params = new URLSearchParams();
  appendMulti(params, "region", filters?.region);
  appendMulti(params, "market", filters?.market);
  appendMulti(params, "area", filters?.area);
  if (filters?.site_id) params.set("site_id", filters.site_id);
  if (filters?.vendor) params.set("vendor", filters.vendor);
  if (filters?.user_id) params.set("user_id", filters.user_id);
  if (filters?.consider_vendor_capacity) params.set("consider_vendor_capacity", "true");
  if (filters?.pace_constraint_flag) params.set("pace_constraint_flag", "true");
  if (filters?.status) params.set("status", filters.status);
  const qs = params.toString();
  return fetchAPI<DashboardSummary>(`/api/v1/schedular/dashboard/sla-default-summary${qs ? `?${qs}` : ""}`);
}

export async function getDashboardSlaSummary(params: {
  date_from: string;
  date_to: string;
  region?: string[];
  market?: string[];
  area?: string[];
}): Promise<DashboardSlaSummary> {
  const sp = new URLSearchParams();
  sp.set("date_from", params.date_from);
  sp.set("date_to", params.date_to);
  appendMulti(sp, "region", params.region);
  appendMulti(sp, "market", params.market);
  appendMulti(sp, "area", params.area);
  return fetchAPI<DashboardSlaSummary>(`/api/v1/schedular/dashboard/sla-history-summary?${sp}`);
}

/* ── Weekly Status ────────────────────────────────────────────────── */

export async function getWeeklyStatusDefault(filters?: {
  region?: string[];
  market?: string[];
  area?: string[];
  site_id?: string;
  vendor?: string;
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  status?: string;
  sla_type?: string;
}): Promise<WeeklyStatusResponse> {
  const params = new URLSearchParams();
  appendMulti(params, "region", filters?.region);
  appendMulti(params, "market", filters?.market);
  appendMulti(params, "area", filters?.area);
  if (filters?.site_id) params.set("site_id", filters.site_id);
  if (filters?.vendor) params.set("vendor", filters.vendor);
  if (filters?.user_id) params.set("user_id", filters.user_id);
  if (filters?.consider_vendor_capacity) params.set("consider_vendor_capacity", "true");
  if (filters?.pace_constraint_flag) params.set("pace_constraint_flag", "true");
  if (filters?.status) params.set("status", filters.status);
  if (filters?.sla_type) params.set("sla_type", filters.sla_type);
  const qs = params.toString();
  return fetchAPI<WeeklyStatusResponse>(`/api/v1/schedular/dashboard/weekly-status-sla-default${qs ? `?${qs}` : ""}`);
}

export async function getWeeklyStatusHistory(params: {
  date_from: string;
  date_to: string;
  region?: string[];
  market?: string[];
  area?: string[];
  site_id?: string;
  vendor?: string;
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  status?: string;
}): Promise<WeeklyStatusResponse> {
  const sp = new URLSearchParams();
  sp.set("date_from", params.date_from);
  sp.set("date_to", params.date_to);
  appendMulti(sp, "region", params.region);
  appendMulti(sp, "market", params.market);
  appendMulti(sp, "area", params.area);
  if (params.site_id) sp.set("site_id", params.site_id);
  if (params.vendor) sp.set("vendor", params.vendor);
  if (params.user_id) sp.set("user_id", params.user_id);
  if (params.consider_vendor_capacity) sp.set("consider_vendor_capacity", "true");
  if (params.pace_constraint_flag) sp.set("pace_constraint_flag", "true");
  if (params.status) sp.set("status", params.status);
  return fetchAPI<WeeklyStatusResponse>(`/api/v1/schedular/dashboard/weekly-status-sla-history?${sp}`);
}

/* ── Gantt Charts — Dashboard (with user_id) ──────────────────────── */

export async function getGanttDashboard(filters?: {
  user_id?: string;
  region?: string[];
  market?: string[];
  area?: string[];
}): Promise<DashboardSummary> {
  const params = new URLSearchParams();
  if (filters?.user_id) params.set("user_id", filters.user_id);
  appendMulti(params, "region", filters?.region);
  appendMulti(params, "market", filters?.market);
  appendMulti(params, "area", filters?.area);
  const qs = params.toString();
  return fetchAPI<DashboardSummary>(`/api/v1/schedular/gantt-charts/dashboard${qs ? `?${qs}` : ""}`);
}

/* ── Constraints ──────────────────────────────────────────────────── */

export async function getConstraints(): Promise<ConstraintThreshold[]> {
  return fetchAPI<ConstraintThreshold[]>("/api/v1/schedular/constraints");
}

export async function getMilestoneConstraints(): Promise<ConstraintThreshold[]> {
  return fetchAPI<ConstraintThreshold[]>("/api/v1/schedular/constraints/milestone");
}

export async function getOverallConstraints(): Promise<ConstraintThreshold[]> {
  return fetchAPI<ConstraintThreshold[]>("/api/v1/schedular/constraints/overall");
}

export async function getConstraintById(id: number): Promise<ConstraintThreshold> {
  return fetchAPI<ConstraintThreshold>(`/api/v1/schedular/constraints/${id}`);
}

export async function createConstraint(body: ConstraintThresholdCreate): Promise<ConstraintThreshold> {
  return fetchAPI<ConstraintThreshold>("/api/v1/schedular/constraints", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function updateConstraint(id: number, body: ConstraintThresholdUpdate): Promise<ConstraintThreshold> {
  return fetchAPI<ConstraintThreshold>(`/api/v1/schedular/constraints/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function deleteConstraint(id: number): Promise<{ detail: string }> {
  return fetchAPI<{ detail: string }>(`/api/v1/schedular/constraints/${id}`, { method: "DELETE" });
}

/* ── Prerequisites ────────────────────────────────────────────────── */

export async function getPrerequisites(): Promise<PrerequisiteDefinition[]> {
  return fetchAPI<PrerequisiteDefinition[]>("/api/v1/schedular/prerequisites");
}

export async function getPrerequisiteFlowchart(): Promise<string> {
  const res = await fetch(`${API_BASE}/api/v1/schedular/prerequisites/flowchart`, { cache: "no-store" });
  if (!res.ok) {
    let detail = `API error: ${res.status}`;
    try {
      const body = await res.json();
      if (body.detail) detail = body.detail;
    } catch { /* ignore parse errors */ }
    throw new Error(detail);
  }
  return res.text();
}

/* ── Gate Checks ──────────────────────────────────────────────────── */

export async function getGateCheckPlanTypes(): Promise<string[]> {
  return fetchAPI<string[]>("/api/v1/schedular/gate-checks/por_plan_type");
}

export async function getGateCheckDevInitiatives(): Promise<string[]> {
  return fetchAPI<string[]>("/api/v1/schedular/gate-checks/por_regional_dev_initiatives");
}

export async function saveGateChecks(body: {
  user_id: string;
  plan_type_include?: string[] | null;
  regional_dev_initiatives?: string | null;
}): Promise<GateCheckConfig> {
  return fetchAPI<GateCheckConfig>("/api/v1/schedular/gate-checks", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getGateChecks(userId: string): Promise<GateCheckConfig> {
  return fetchAPI<GateCheckConfig>(`/api/v1/schedular/gate-checks/${userId}`);
}

/* ── User Filters ─────────────────────────────────────────────────── */

export async function getUserFilters(userId: string): Promise<UserFilter> {
  return fetchAPI<UserFilter>(`/api/v1/schedular/user-filters/${userId}`);
}

export async function deleteUserFilters(userId: string): Promise<void> {
  await fetchAPI<void>(`/api/v1/schedular/user-filters/${userId}`, { method: "DELETE" });
}

/* ── User Expected Days ───────────────────────────────────────────── */

export async function getUserExpectedDays(userId: string): Promise<UserExpectedDaysEntry[]> {
  return fetchAPI<UserExpectedDaysEntry[]>(`/api/v1/schedular/user-expected-days/${userId}`);
}

export async function setUserExpectedDays(userId: string, body: {
  milestone_key: string;
  expected_days: number;
}): Promise<UserExpectedDaysEntry> {
  return fetchAPI<UserExpectedDaysEntry>(`/api/v1/schedular/user-expected-days/${userId}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function deleteUserExpectedDays(userId: string, milestoneKey: string): Promise<{ detail: string }> {
  return fetchAPI<{ detail: string }>(`/api/v1/schedular/user-expected-days/${userId}/${milestoneKey}`, {
    method: "DELETE",
  });
}

/* ── Skip Prerequisites (user-level) ─────────────────────────────── */

export async function skipPrerequisite(body: { user_id: string; milestone_key: string }): Promise<SkippedPrerequisite> {
  return fetchAPI<SkippedPrerequisite>("/api/v1/schedular/skip-prerequisites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function getUserSkippedPrerequisites(userId: string): Promise<SkippedPrerequisite[]> {
  return fetchAPI<SkippedPrerequisite[]>(`/api/v1/schedular/skip-prerequisites/${userId}`);
}

export async function unskipPrerequisite(userId: string, milestoneKey: string): Promise<{ detail: string }> {
  return fetchAPI<{ detail: string }>(`/api/v1/schedular/skip-prerequisites/${userId}/${milestoneKey}`, { method: "DELETE" });
}

export async function unskipAllPrerequisites(userId: string): Promise<{ detail: string }> {
  return fetchAPI<{ detail: string }>(`/api/v1/schedular/skip-prerequisites/${userId}`, { method: "DELETE" });
}

/* ── SLA History ──────────────────────────────────────────────────── */

export async function getSlaHistoryGantt(params: {
  date_from: string;
  date_to: string;
  region?: string[];
  market?: string[];
  area?: string[];
  site_id?: string;
  vendor?: string;
  user_id?: string;
  limit?: number;
  offset?: number;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  status?: string;
}): Promise<SlaHistoryGanttResponse> {
  const sp = new URLSearchParams();
  sp.set("date_from", params.date_from);
  sp.set("date_to", params.date_to);
  appendMulti(sp, "region", params.region);
  appendMulti(sp, "market", params.market);
  appendMulti(sp, "area", params.area);
  if (params.site_id) sp.set("site_id", params.site_id);
  if (params.vendor) sp.set("vendor", params.vendor);
  if (params.user_id) sp.set("user_id", params.user_id);
  if (params.limit) sp.set("limit", String(params.limit));
  if (params.offset) sp.set("offset", String(params.offset));
  if (params.consider_vendor_capacity) sp.set("consider_vendor_capacity", "true");
  if (params.pace_constraint_flag) sp.set("pace_constraint_flag", "true");
  if (params.status) sp.set("status", params.status);
  return fetchAPI<SlaHistoryGanttResponse>(`/api/v1/schedular/sla-history/gantt-charts?${sp}`);
}

/* ── SLA History — Reset ──────────────────────────────────────────── */

export async function resetSlaHistory(userId?: string): Promise<{ detail: string }> {
  const params = userId ? `?user_id=${encodeURIComponent(userId)}` : "";
  return fetchAPI<{ detail: string }>(`/api/v1/schedular/history-sla-days/reset${params}`, { method: "POST" });
}

export async function getUserHistoryExpectedDays(userId: string): Promise<UserHistoryExpectedDaysEntry[]> {
  return fetchAPI<UserHistoryExpectedDaysEntry[]>(`/api/v1/schedular/history-sla-days/${encodeURIComponent(userId)}`);
}

/* ── Admin ────────────────────────────────────────────────────────── */

export async function getStagingColumns(): Promise<string[]> {
  return fetchAPI<string[]>("/api/v1/schedular/admin/staging-columns");
}

export async function createPrerequisite(body: MilestoneDefinitionCreate): Promise<PrerequisiteDefinition> {
  return fetchAPI<PrerequisiteDefinition>("/api/v1/schedular/admin/prerequisites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function updatePrerequisite(id: number, body: MilestoneDefinitionUpdate): Promise<PrerequisiteDefinition> {
  return fetchAPI<PrerequisiteDefinition>(`/api/v1/schedular/admin/prerequisites/${id}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function adminSkipPrerequisite(milestoneKey: string): Promise<SkippedPrerequisite> {
  return fetchAPI<SkippedPrerequisite>("/api/v1/schedular/admin/skip-prerequisites", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ milestone_key: milestoneKey }),
  });
}

export async function adminGetSkippedPrerequisites(): Promise<SkippedPrerequisite[]> {
  return fetchAPI<SkippedPrerequisite[]>("/api/v1/schedular/admin/skip-prerequisites");
}

export async function adminUnskipPrerequisite(milestoneKey: string): Promise<{ detail: string }> {
  return fetchAPI<{ detail: string }>(`/api/v1/schedular/admin/skip-prerequisites/${milestoneKey}`, { method: "DELETE" });
}

export async function adminUnskipAllPrerequisites(): Promise<{ detail: string }> {
  return fetchAPI<{ detail: string }>("/api/v1/schedular/admin/skip-prerequisites", { method: "DELETE" });
}

/* ── Assistant / Chat ─────────────────────────────────────────────── */

export async function createThread(userId: string): Promise<{ thread_id: string; user_id: string }> {
  return fetchAPI<{ thread_id: string; user_id: string }>("/api/v1/schedular/assistant/threads", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ user_id: userId }),
  });
}

export async function sendChat(params: {
  message: string;
  user_id: string;
  thread_id: string;
}): Promise<ChatResponse> {
  const sp = new URLSearchParams();
  sp.set("user_id", params.user_id);
  sp.set("thread_id", params.thread_id);
  return fetchAPI<ChatResponse>(`/api/v1/schedular/assistant/chat?${sp}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message: params.message }),
  });
}

export async function resumeSimulation(params: {
  thread_id: string;
  clarification: string;
}): Promise<Record<string, unknown>> {
  return fetchAPI<Record<string, unknown>>("/api/v1/schedular/resume", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(params),
  });
}

export async function getChatHistory(): Promise<ChatHistoryUser[]> {
  return fetchAPI<ChatHistoryUser[]>("/api/v1/schedular/assistant/history");
}

export async function getUserThreads(userId: string): Promise<ChatThreadSummary[]> {
  return fetchAPI<ChatThreadSummary[]>(`/api/v1/schedular/assistant/history/${userId}/threads`);
}

export async function getThreadMessages(userId: string, threadId: string): Promise<ChatThread> {
  return fetchAPI<ChatThread>(`/api/v1/schedular/assistant/history/${userId}/threads/${threadId}`);
}

export async function deleteThread(userId: string, threadId: string): Promise<{ detail: string }> {
  return fetchAPI<{ detail: string }>(`/api/v1/schedular/assistant/history/${userId}/threads/${threadId}`, {
    method: "DELETE",
  });
}

export async function deleteUserHistory(userId: string): Promise<{ detail: string }> {
  return fetchAPI<{ detail: string }>(`/api/v1/schedular/assistant/history/${userId}`, {
    method: "DELETE",
  });
}

/* ── Export ────────────────────────────────────────────────────────── */

export function getExportCsvUrl(filters?: {
  region?: string[];
  market?: string[];
  area?: string[];
  site_id?: string;
  vendor?: string;
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  status?: string;
}): string {
  const params = new URLSearchParams();
  appendMulti(params, "region", filters?.region);
  appendMulti(params, "market", filters?.market);
  appendMulti(params, "area", filters?.area);
  if (filters?.site_id) params.set("site_id", filters.site_id);
  if (filters?.vendor) params.set("vendor", filters.vendor);
  if (filters?.user_id) params.set("user_id", filters.user_id);
  if (filters?.consider_vendor_capacity) params.set("consider_vendor_capacity", "true");
  if (filters?.pace_constraint_flag) params.set("pace_constraint_flag", "true");
  if (filters?.status) params.set("status", filters.status);
  const qs = params.toString();
  return `${API_BASE}/api/v1/schedular/export/gantt-csv${qs ? `?${qs}` : ""}`;
}

export function getExportCsvHistoryUrl(filters: {
  date_from: string;
  date_to: string;
  region?: string[];
  market?: string[];
  area?: string[];
  site_id?: string;
  vendor?: string;
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  status?: string;
}): string {
  const params = new URLSearchParams();
  params.set("date_from", filters.date_from);
  params.set("date_to", filters.date_to);
  appendMulti(params, "region", filters.region);
  appendMulti(params, "market", filters.market);
  appendMulti(params, "area", filters.area);
  if (filters.site_id) params.set("site_id", filters.site_id);
  if (filters.vendor) params.set("vendor", filters.vendor);
  if (filters.user_id) params.set("user_id", filters.user_id);
  if (filters.consider_vendor_capacity) params.set("consider_vendor_capacity", "true");
  if (filters.pace_constraint_flag) params.set("pace_constraint_flag", "true");
  if (filters.status) params.set("status", filters.status);
  return `${API_BASE}/api/v1/schedular/export/gantt-csv-history?${params}`;
}

/* ── GC Capacity (read-only) ───────────────────────────────────────── */

export async function getGcCapacities(): Promise<GcCapacityEntry[]> {
  return fetchAPI<GcCapacityEntry[]>("/api/v1/schedular/gc-capacity");
}

/* ── Pace Constraints ─────────────────────────────────────────────── */

export async function getPaceConstraints(userId: string): Promise<PaceConstraintEntry[]> {
  return fetchAPI<PaceConstraintEntry[]>(`/api/v1/schedular/pace-constraints?user_id=${encodeURIComponent(userId)}`);
}

export async function createPaceConstraint(body: PaceConstraintCreate): Promise<PaceConstraintEntry> {
  return fetchAPI<PaceConstraintEntry>("/api/v1/schedular/pace-constraints", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function updatePaceConstraint(id: number, userId: string, body: PaceConstraintUpdate): Promise<PaceConstraintEntry> {
  return fetchAPI<PaceConstraintEntry>(`/api/v1/schedular/pace-constraints/${id}?user_id=${encodeURIComponent(userId)}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function deletePaceConstraint(id: number, userId: string): Promise<{ detail: string }> {
  return fetchAPI<{ detail: string }>(`/api/v1/schedular/pace-constraints/${id}?user_id=${encodeURIComponent(userId)}`, { method: "DELETE" });
}

/* ── Analytics ────────────────────────────────────────────────────── */

export async function getPendingMilestonesAuto(filters?: {
  region?: string[];
  market?: string[];
  site_id?: string;
  vendor?: string;
  area?: string[];
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  filter_date_from?: string;
  filter_date_to?: string;
}): Promise<PendingMilestonesResponse> {
  const params = new URLSearchParams();
  appendMulti(params, "region", filters?.region);
  appendMulti(params, "market", filters?.market);
  if (filters?.site_id) params.set("site_id", filters.site_id);
  if (filters?.vendor) params.set("vendor", filters.vendor);
  appendMulti(params, "area", filters?.area);
  if (filters?.user_id) params.set("user_id", filters.user_id);
  if (filters?.consider_vendor_capacity) params.set("consider_vendor_capacity", "true");
  if (filters?.pace_constraint_flag) params.set("pace_constraint_flag", "true");
  if (filters?.filter_date_from) params.set("filter_date_from", filters.filter_date_from);
  if (filters?.filter_date_to) params.set("filter_date_to", filters.filter_date_to);
  const qs = params.toString();
  return fetchAPI<PendingMilestonesResponse>(`/api/v1/schedular/analytics/pending-milestones/auto${qs ? `?${qs}` : ""}`);
}

export async function getPendingMilestonesSlaHistory(params: {
  date_from: string;
  date_to: string;
  region?: string[];
  market?: string[];
  site_id?: string;
  vendor?: string;
  area?: string[];
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  filter_date_from?: string;
  filter_date_to?: string;
}): Promise<PendingMilestonesResponse> {
  const sp = new URLSearchParams();
  sp.set("date_from", params.date_from);
  sp.set("date_to", params.date_to);
  appendMulti(sp, "region", params.region);
  appendMulti(sp, "market", params.market);
  if (params.site_id) sp.set("site_id", params.site_id);
  if (params.vendor) sp.set("vendor", params.vendor);
  appendMulti(sp, "area", params.area);
  if (params.user_id) sp.set("user_id", params.user_id);
  if (params.consider_vendor_capacity) sp.set("consider_vendor_capacity", "true");
  if (params.pace_constraint_flag) sp.set("pace_constraint_flag", "true");
  if (params.filter_date_from) sp.set("filter_date_from", params.filter_date_from);
  if (params.filter_date_to) sp.set("filter_date_to", params.filter_date_to);
  return fetchAPI<PendingMilestonesResponse>(`/api/v1/schedular/analytics/pending-milestones/sla-history?${sp}`);
}

export async function getPendingByMilestoneAuto(filters?: {
  region?: string[];
  market?: string[];
  site_id?: string;
  vendor?: string;
  area?: string[];
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  filter_date_from?: string;
  filter_date_to?: string;
}): Promise<PendingByMilestoneResponse> {
  const params = new URLSearchParams();
  appendMulti(params, "region", filters?.region);
  appendMulti(params, "market", filters?.market);
  if (filters?.site_id) params.set("site_id", filters.site_id);
  if (filters?.vendor) params.set("vendor", filters.vendor);
  appendMulti(params, "area", filters?.area);
  if (filters?.user_id) params.set("user_id", filters.user_id);
  if (filters?.consider_vendor_capacity) params.set("consider_vendor_capacity", "true");
  if (filters?.pace_constraint_flag) params.set("pace_constraint_flag", "true");
  if (filters?.filter_date_from) params.set("filter_date_from", filters.filter_date_from);
  if (filters?.filter_date_to) params.set("filter_date_to", filters.filter_date_to);
  const qs = params.toString();
  return fetchAPI<PendingByMilestoneResponse>(`/api/v1/schedular/analytics/pending-by-milestone/auto${qs ? `?${qs}` : ""}`);
}

export async function getPendingByMilestoneSlaHistory(params: {
  date_from: string;
  date_to: string;
  region?: string[];
  market?: string[];
  site_id?: string;
  vendor?: string;
  area?: string[];
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  filter_date_from?: string;
  filter_date_to?: string;
}): Promise<PendingByMilestoneResponse> {
  const sp = new URLSearchParams();
  sp.set("date_from", params.date_from);
  sp.set("date_to", params.date_to);
  appendMulti(sp, "region", params.region);
  appendMulti(sp, "market", params.market);
  if (params.site_id) sp.set("site_id", params.site_id);
  if (params.vendor) sp.set("vendor", params.vendor);
  appendMulti(sp, "area", params.area);
  if (params.user_id) sp.set("user_id", params.user_id);
  if (params.consider_vendor_capacity) sp.set("consider_vendor_capacity", "true");
  if (params.pace_constraint_flag) sp.set("pace_constraint_flag", "true");
  if (params.filter_date_from) sp.set("filter_date_from", params.filter_date_from);
  if (params.filter_date_to) sp.set("filter_date_to", params.filter_date_to);
  return fetchAPI<PendingByMilestoneResponse>(`/api/v1/schedular/analytics/pending-by-milestone/sla-history?${sp}`);
}

export async function getDrilldownAuto(params: {
  drilldown_type: string;
  pending_count?: number;
  milestone_key?: string;
  region?: string[];
  market?: string[];
  site_id?: string;
  vendor?: string;
  area?: string[];
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  filter_date_from?: string;
  filter_date_to?: string;
}): Promise<DrilldownResponse> {
  const sp = new URLSearchParams();
  sp.set("drilldown_type", params.drilldown_type);
  if (params.pending_count !== undefined && params.pending_count !== null) sp.set("pending_count", String(params.pending_count));
  if (params.milestone_key) sp.set("milestone_key", params.milestone_key);
  appendMulti(sp, "region", params.region);
  appendMulti(sp, "market", params.market);
  if (params.site_id) sp.set("site_id", params.site_id);
  if (params.vendor) sp.set("vendor", params.vendor);
  appendMulti(sp, "area", params.area);
  if (params.user_id) sp.set("user_id", params.user_id);
  if (params.consider_vendor_capacity) sp.set("consider_vendor_capacity", "true");
  if (params.pace_constraint_flag) sp.set("pace_constraint_flag", "true");
  if (params.filter_date_from) sp.set("filter_date_from", params.filter_date_from);
  if (params.filter_date_to) sp.set("filter_date_to", params.filter_date_to);
  return fetchAPI<DrilldownResponse>(`/api/v1/schedular/analytics/drilldown/auto?${sp}`);
}

export async function getDrilldownSlaHistory(params: {
  date_from: string;
  date_to: string;
  drilldown_type: string;
  pending_count?: number;
  milestone_key?: string;
  region?: string[];
  market?: string[];
  site_id?: string;
  vendor?: string;
  area?: string[];
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  filter_date_from?: string;
  filter_date_to?: string;
}): Promise<DrilldownResponse> {
  const sp = new URLSearchParams();
  sp.set("date_from", params.date_from);
  sp.set("date_to", params.date_to);
  sp.set("drilldown_type", params.drilldown_type);
  if (params.pending_count !== undefined && params.pending_count !== null) sp.set("pending_count", String(params.pending_count));
  if (params.milestone_key) sp.set("milestone_key", params.milestone_key);
  appendMulti(sp, "region", params.region);
  appendMulti(sp, "market", params.market);
  if (params.site_id) sp.set("site_id", params.site_id);
  if (params.vendor) sp.set("vendor", params.vendor);
  appendMulti(sp, "area", params.area);
  if (params.user_id) sp.set("user_id", params.user_id);
  if (params.consider_vendor_capacity) sp.set("consider_vendor_capacity", "true");
  if (params.pace_constraint_flag) sp.set("pace_constraint_flag", "true");
  if (params.filter_date_from) sp.set("filter_date_from", params.filter_date_from);
  if (params.filter_date_to) sp.set("filter_date_to", params.filter_date_to);
  return fetchAPI<DrilldownResponse>(`/api/v1/schedular/analytics/drilldown/sla-history?${sp}`);
}

/* ── CX Forecast Summary ──────────────────────────────────────────── */

export async function getCxForecastSummary(filters?: {
  start_date?: string;
  end_date?: string;
  region?: string[];
  market?: string[];
  site_id?: string;
  vendor?: string;
  area?: string[];
  user_id?: string;
}): Promise<CxForecastSummaryResponse> {
  const params = new URLSearchParams();
  if (filters?.start_date) params.set("start_date", filters.start_date);
  if (filters?.end_date) params.set("end_date", filters.end_date);
  appendMulti(params, "region", filters?.region);
  appendMulti(params, "market", filters?.market);
  if (filters?.site_id) params.set("site_id", filters.site_id);
  if (filters?.vendor) params.set("vendor", filters.vendor);
  appendMulti(params, "area", filters?.area);
  if (filters?.user_id) params.set("user_id", filters.user_id);
  const qs = params.toString();
  return fetchAPI<CxForecastSummaryResponse>(`/api/v1/schedular/cx-forecast-summary${qs ? `?${qs}` : ""}`);
}

/* ── CX Actual Summary ────────────────────────────────────────────── */

export async function getCxActualSummary(filters?: {
  start_date?: string;
  end_date?: string;
  region?: string[];
  market?: string[];
  site_id?: string;
  vendor?: string;
  area?: string[];
  user_id?: string;
}): Promise<CxActualSummaryResponse> {
  const params = new URLSearchParams();
  if (filters?.start_date) params.set("start_date", filters.start_date);
  if (filters?.end_date) params.set("end_date", filters.end_date);
  appendMulti(params, "region", filters?.region);
  appendMulti(params, "market", filters?.market);
  if (filters?.site_id) params.set("site_id", filters.site_id);
  if (filters?.vendor) params.set("vendor", filters.vendor);
  appendMulti(params, "area", filters?.area);
  if (filters?.user_id) params.set("user_id", filters.user_id);
  const qs = params.toString();
  return fetchAPI<CxActualSummaryResponse>(`/api/v1/schedular/cx-actual-summary${qs ? `?${qs}` : ""}`);
}

/* ── Calendar ──────────────────────────────────────────────────────── */

export async function getCalendarSites(filters: {
  start_date: string;
  end_date: string;
  region?: string[];
  market?: string[];
  site_id?: string;
  vendor?: string;
  area?: string[];
  user_id?: string;
  consider_vendor_capacity?: boolean;
  pace_constraint_flag?: boolean;
  status?: string;
  sla_type?: string;
}): Promise<{ sla_type: string; start_date: string; end_date: string; count: number; sites: SiteGantt[] }> {
  const sp = new URLSearchParams();
  sp.set("start_date", filters.start_date);
  sp.set("end_date", filters.end_date);
  appendMulti(sp, "region", filters.region);
  appendMulti(sp, "market", filters.market);
  if (filters.site_id) sp.set("site_id", filters.site_id);
  if (filters.vendor) sp.set("vendor", filters.vendor);
  appendMulti(sp, "area", filters.area);
  if (filters.user_id) sp.set("user_id", filters.user_id);
  if (filters.consider_vendor_capacity) sp.set("consider_vendor_capacity", "true");
  if (filters.pace_constraint_flag) sp.set("pace_constraint_flag", "true");
  if (filters.status) sp.set("status", filters.status);
  if (filters.sla_type) sp.set("sla_type", filters.sla_type);
  return fetchAPI(`/api/v1/schedular/calendar?${sp}`);
}

/* ── Health ────────────────────────────────────────────────────────── */

export async function healthCheck(): Promise<{ status: string; service: string }> {
  return fetchAPI<{ status: string; service: string }>("/api/health");
}
