/* ── Milestone & Gantt ─────────────────────────────────────────────── */

export interface Milestone {
  key: string;
  name: string;
  sort_order: number;
  expected_days: number;
  task_owner: string | null;
  phase_type: string | null;
  preceding_milestones: string[];
  following_milestones: string[];
  planned_start: string | null;
  planned_finish: string | null;
  actual_finish: string | null;
  delay_days: number;
  status: string;
}

export interface MilestoneStatusSummary {
  total: number;
  on_track: number;
  in_progress: number;
  delayed: number;
}

export interface SiteGantt {
  vendor_name: string;
  site_id: string;
  project_id: string;
  project_name: string;
  market: string;
  area: string;
  region: string;
  delay_comments: string | null;
  delay_code: string | null;
  forecasted_cx_start_date: string | null;
  milestones: Milestone[];
  overall_status: string;
  on_track_pct: number;
  milestone_status_summary: MilestoneStatusSummary;
}

export interface GanttResponse {
  count: number;
  sites: SiteGantt[];
  pagination: {
    limit: number | null;
    offset: number | null;
    total_count: number;
  };
}

/* ── Filters ──────────────────────────────────────────────────────── */

export interface FilterOptions {
  regions: string[];
  markets: string[];
  areas: string[];
  site_ids: string[];
  vendors: string[];
}

/* ── Dashboard ────────────────────────────────────────────────────── */

export interface DashboardSummary {
  dashboard_status: string;
  on_track_pct: number;
  total_sites: number;
  on_track_sites: number;
  in_progress_sites: number;
  critical_sites: number;
  blocked_sites: number;
}

export interface DashboardSlaSummary extends DashboardSummary {
  sla_type: string;
  date_from: string;
  date_to: string;
  sla_milestones: SlaMilestone[];
}

export interface SlaMilestone {
  milestone_key: string;
  milestone_name: string;
  default_expected_days: number;
  history_expected_days: number | null;
  sample_count: number;
  is_skipped: boolean;
}

/* ── Constraints ──────────────────────────────────────────────────── */

export interface ConstraintThreshold {
  id: number;
  constraint_type: string;
  name: string;
  status_label: string;
  color: string;
  min_pct: number;
  max_pct: number | null;
  sort_order: number;
}

/* ── Prerequisites ────────────────────────────────────────────────── */

export interface PrerequisiteDefinition {
  id: number;
  key: string;
  name: string;
  sort_order: number;
  expected_days: number;
  history_expected_days: number | null;
  start_gap_days: number;
  sla_type: string;
  task_owner: string | null;
  phase_type: string | null;
  preceding_milestones: string[];
  following_milestones: string[];
}

/* ── Admin — Prerequisite CRUD ────────────────────────────────────── */

export interface MilestoneColumnCreate {
  column_name: string;
  column_role: string;
  logic: string | null;
}

export interface MilestoneDefinitionCreate {
  key: string;
  name: string;
  expected_days: number;
  start_gap_days?: number;
  task_owner?: string | null;
  phase_type?: string | null;
  preceding_milestone_keys?: string[];
  following_milestone_keys?: string[];
  insert_after_key?: string | null;
  columns: MilestoneColumnCreate[];
}

export interface MilestoneDefinitionUpdate {
  name?: string;
  expected_days?: number;
  start_gap_days?: number;
  task_owner?: string | null;
  phase_type?: string | null;
}

export interface SkippedPrerequisite {
  id: number;
  key: string;
  name: string;
  is_skipped: boolean;
}

export interface ConstraintThresholdCreate {
  constraint_type: string;
  name: string;
  status_label: string;
  color: string;
  min_pct: number;
  max_pct?: number | null;
  sort_order?: number;
}

export interface ConstraintThresholdUpdate {
  name?: string;
  status_label?: string;
  color?: string;
  min_pct?: number;
  max_pct?: number | null;
  sort_order?: number;
}

export interface UserExpectedDaysEntry {
  id: number;
  user_id: string;
  milestone_key: string;
  expected_days: number;
}

export interface GateCheckConfig {
  user_id: string;
  plan_type_include: string[] | null;
  regional_dev_initiatives: string | null;
}

/* ── Assistant / Chat ─────────────────────────────────────────────── */

export interface ChatResponse {
  message: string;
  actions: ChatAction[];
  hitl_required?: boolean;
  thread_id?: string;
  clarification?: Record<string, unknown>;
}

export interface ChatAction {
  method: string;
  endpoint: string;
  params: Record<string, string>;
}

/* ── User Filters ─────────────────────────────────────────────────── */

export interface UserFilter {
  id: number;
  user_id: string;
  region: string | null;
  market: string | null;
  vendor: string | null;
  site_id: string | null;
  area: string | null;
  plan_type_include: string | null;
  regional_dev_initiatives: string | null;
}

/* ── SLA History ──────────────────────────────────────────────────── */

export interface SlaHistoryGanttResponse {
  sla_type: string;
  date_from: string;
  date_to: string;
  count: number;
  sites: SiteGantt[];
  pagination: {
    limit: number | null;
    offset: number | null;
    total_count: number;
  };
}
