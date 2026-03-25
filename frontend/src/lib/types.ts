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
  note: string | null;
  milestones: Milestone[];
  overall_status: string;
  on_track_pct: number;
  milestone_status_summary: MilestoneStatusSummary;
  excluded_due_to_crew_shortage?: boolean;
  excluded_due_to_pace_constraint?: boolean;
  exclude_reason?: string | null;
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
  plan_types: string[];
  dev_initiatives: string[];
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
  excluded_crew_shortage_sites: number;
  excluded_pace_constraint_sites: number;
  pace_constraint_max_sites: number;
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
  updated_at: string | null;
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

export interface UserHistoryExpectedDaysEntry {
  id: number;
  user_id: string;
  milestone_key: string;
  milestone_name: string | null;
  history_expected_days: number;
  date_from: string | null;
  date_to: string | null;
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

/* ── Chat History ─────────────────────────────────────────────────── */

export interface ChatMessageEntry {
  id: number;
  role: string;
  content: string;
  created_at: string | null;
}

export interface ChatThreadSummary {
  thread_id: string;
  message_count: number;
  first_user_message: string | null;
  first_assistant_message: string | null;
  last_message_at: string | null;
}

export interface ChatThread {
  thread_id: string;
  messages: ChatMessageEntry[];
  last_message_at: string | null;
}

export interface ChatHistoryUser {
  user_id: string;
  threads: ChatThread[];
}

/* ── SLA History ──────────────────────────────────────────────────── */

/* ── GC Capacity ─────────────────────────────────────────────────── */

export interface GcCapacityEntry {
  id: number;
  gc_company: string;
  market: string;
  day_wise_gc_capacity: number;
}

export interface GcCapacityCreate {
  gc_company: string;
  market: string;
  day_wise_gc_capacity: number;
}

export interface GcCapacityUpdate {
  gc_company?: string;
  market?: string;
  day_wise_gc_capacity?: number;
}

/* ── Pace Constraints ────────────────────────────────────────────── */

export interface PaceConstraintEntry {
  id: number;
  start_date: string | null;
  end_date: string | null;
  market: string | null;
  area: string | null;
  region: string | null;
  max_sites: number;
}

export interface PaceConstraintCreate {
  user_id: string;
  start_date: string | null;
  end_date: string | null;
  market?: string | null;
  area?: string | null;
  region?: string | null;
  max_sites: number;
}

export interface PaceConstraintUpdate {
  start_date?: string;
  end_date?: string;
  market?: string | null;
  area?: string | null;
  region?: string | null;
  max_sites?: number;
}

/* ── Analytics ────────────────────────────────────────────────────── */

export interface PendingMilestoneBucket {
  pending_milestone_count: number;
  site_count: number;
}

export interface PendingMilestonesResponse {
  sla_type: string;
  total_sites: number;
  blocked_sites: number;
  pending_milestones: PendingMilestoneBucket[];
  date_from?: string;
  date_to?: string;
}

export interface MilestonePendingSites {
  milestone_key: string;
  milestone_name: string;
  pending_site_count: number;
  sort_order: number;
}

export interface PendingByMilestoneResponse {
  sla_type: string;
  total_sites: number;
  blocked_sites: number;
  milestones: MilestonePendingSites[];
  date_from?: string;
  date_to?: string;
}

export interface DrilldownResponse {
  drilldown_type: string;
  pending_count: number | null;
  milestone_key: string | null;
  count: number;
  blocked_sites: number;
  sites: SiteGantt[];
  date_from?: string;
  date_to?: string;
}

export interface SlaHistoryGanttResponse {
  sla_type: string;
  date_from: string;
  date_to: string;
  sla_last_updated: string | null;
  count: number;
  sites: SiteGantt[];
  pagination: {
    limit: number | null;
    offset: number | null;
    total_count: number;
  };
}
