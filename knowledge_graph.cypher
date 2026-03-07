// ============================================================================
// NOKIA CONSTRUCTION FORECAST — BUSINESS KNOWLEDGE GRAPH
// Designed for LLM agent traversal. Nodes are rich, self-contained knowledge
// units. An agent should be able to answer any question by visiting 1-3 nodes.
// ============================================================================

MATCH (n) DETACH DELETE n;

// ============================================================================
// NODE 1: THE PREREQUISITE CHAIN (complete definition in one place)
// An agent asking "what are the prerequisites?" or "what depends on what?"
// gets everything from this single node.
// ============================================================================

CREATE (:PrerequisiteChain {
  name: 'Construction Prerequisite Chain',

  purpose: 'Defines all 14 prerequisites that must be completed before construction can start on a telecom site. Prerequisites are organized as a sequential spine followed by five parallel branches. The chain produces a Forecasted Construction Start Date.',

  sequential_spine: '3710(Entitlement Complete, 0d, TMO) -> 1310(Pre-NTP Document, 2d, Proj Ops) -> site_walk(Site Walk Performed, 7d, CM) -> 1323(Ready for Scoping, 3d, SE-CoE) -> 1327(Scoping Validated by GC, 7d, SE-CoE). Total spine: ~23 days. Milestone 1327 is the BRANCH POINT where five parallel paths diverge.',

  branch_1_bom: '3850(BOM in BAT, 0d, TMO) -> 3875(BOM in AIMS, 21d, TMO). NOTE: 3850 has MULTI-DEPENDENCY on both 3710 AND 1327. Starts after whichever finishes LAST. Total: ~22 days. BOM in AIMS at 21d is the single longest prerequisite.',

  branch_2_procurement: 'quote(Quote Submitted, 7d, PM) -> cpo(CPO Available, 14d, PDM) -> 1555(SPO Issued, 5d, PDM). Total: ~27 days. CPO is a TEXT milestone (non-empty = complete). Often the CRITICAL PATH. SPO is a tail milestone (offset +5d).',

  branch_3_materials: 'steel(Steel Received, 14d, GC) -> 3925(Material Pickup, 5d, GC). Total: ~20 days. Steel has WITH_STATUS handler: status A = use date, status N/Not Applicable/empty = skip as On Track (steel not needed). Both are tail milestones (steel +7d, 3925 +4d).',

  branch_4_ntp: '1407(NTP Received, 7d, TMO). Single milestone. Tail with +7d offset. Shortest branch.',

  branch_5_access: '4000(Access Confirmation, 7d, CM). Single milestone. TEXT handler (non-empty = confirmed). Tail with +7d offset.',

  tail_milestones: 'Five tails feed into All Prerequisites Complete via MAX: 3925(+4d offset), steel(+7d), 1555(+5d), 4000(+7d), 1407(+7d). The SLOWEST tail determines the all-prereq-complete date.',

  virtual_milestones: 'all_prereq(All Prerequisites Complete, 0d) = MAX of all tail finishes+offsets. cx_start_forecast(Cx Start Forecast, 4d) = all_prereq + CX_START_OFFSET_DAYS (default 4, configurable).',

  typical_critical_path: 'Spine(23d) + Procurement branch(27d) + tail offset(5d) + CX offset(4d) = ~59 days from entitlement to forecast construction start. BOM branch is close second at ~22d + spine.',

  milestone_details: '[{"key":"3710","name":"Entitlement Complete","expected_days":0,"start_gap_days":1,"depends_on":null,"task_owner":"TMO","phase":"Pre-Con Phase","actual_column":"pj_a_3710_ran_entitlement_complete_finish","planned_column":"pj_p_3710_ran_entitlement_complete_finish","handler":"single","is_root":true,"is_tail":false},{"key":"1310","name":"Pre-NTP Document Received","expected_days":2,"start_gap_days":0,"depends_on":"3710","task_owner":"Proj Ops","phase":"Pre-Con Phase","actual_column":"ms_1310_pre_construction_package_received_actual","handler":"single","is_tail":false},{"key":"site_walk","name":"Site Walk Performed","expected_days":7,"start_gap_days":1,"depends_on":"1310","task_owner":"CM","phase":"Pre-Con Phase","actual_columns":["ms_1316_pre_con_site_walk_completed_actual","ms_1321_talon_view_drone_svcs_actual"],"handler":"max","handler_note":"MAX of site walk + drone dates","is_tail":false},{"key":"1323","name":"Ready for Scoping","expected_days":3,"start_gap_days":1,"depends_on":"site_walk","task_owner":"SE-CoE","phase":"Pre-Con Phase","actual_column":"ms_1323_ready_for_scoping_actual","handler":"single","is_tail":false},{"key":"1327","name":"Scoping Validated by GC","expected_days":7,"start_gap_days":1,"depends_on":"1323","task_owner":"SE-CoE","phase":"Scoping Phase","actual_column":"ms_1327_scoping_and_quoting_package_validated_actual","handler":"single","is_branch_point":true,"is_tail":false},{"key":"3850","name":"BOM in BAT","expected_days":0,"start_gap_days":1,"depends_on":["3710","1327"],"task_owner":"TMO","phase":"Scoping Phase","actual_column":"pj_a_3850_bom_submitted_bom_in_bat_finish","handler":"single","multi_dep_note":"Starts after MAX(pf_3710, pf_1327)","is_tail":false},{"key":"3875","name":"BOM in AIMS","expected_days":21,"start_gap_days":1,"depends_on":"3850","task_owner":"TMO","phase":"Material & NTP Phase","actual_column":"pj_a_3875_bom_received_bom_in_aims_finish","handler":"single","is_tail":false},{"key":"quote","name":"Quote Submitted","expected_days":7,"start_gap_days":1,"depends_on":"1327","task_owner":"PM","phase":"Scoping Phase","actual_column":"ms_1331_scoping_package_submitted_actual","handler":"single","is_tail":false},{"key":"cpo","name":"CPO Available","expected_days":14,"start_gap_days":1,"depends_on":"quote","task_owner":"PDM","phase":"Material & NTP Phase","actual_column":"ms1555_construction_complete_so_header","handler":"text","handler_note":"Non-empty text = complete","is_tail":false},{"key":"1555","name":"SPO Issued","expected_days":5,"start_gap_days":1,"depends_on":"cpo","task_owner":"PDM","phase":"Material & NTP Phase","actual_column":"ms1555_construction_complete_spo_issued_date","handler":"single","history_sla_note":"Walks past text CPO to use Quote as date predecessor","is_tail":true,"tail_offset":5},{"key":"steel","name":"Steel Received","expected_days":14,"start_gap_days":1,"depends_on":"1327","task_owner":"GC","phase":"Material & NTP Phase","actual_column":"pj_steel_received_date","status_column":"pj_steel_received_status","handler":"with_status","handler_note":"A=use date, N/Not Applicable/empty=skip as On Track","is_tail":true,"tail_offset":7},{"key":"3925","name":"Material Pickup by GC","expected_days":5,"start_gap_days":1,"depends_on":"steel","task_owner":"GC","phase":"Material & NTP Phase","actual_column":"pj_a_3925_msl_pickup_date_finish","handler":"single","is_tail":true,"tail_offset":4},{"key":"1407","name":"NTP Received","expected_days":7,"start_gap_days":1,"depends_on":"1327","task_owner":"TMO","phase":"Material & NTP Phase","actual_column":"ms_1407_tower_ntp_validated_actual","handler":"single","is_tail":true,"tail_offset":7},{"key":"4000","name":"Access Confirmation","expected_days":7,"start_gap_days":1,"depends_on":"1327","task_owner":"CM","phase":"Material & NTP Phase","actual_column":"pj_a_4000_ll_ntp_received","handler":"text","handler_note":"Non-empty = access confirmed","is_tail":true,"tail_offset":7}]'
});

// ============================================================================
// NODE 2: THE FORECAST ENGINE (how dates are calculated)
// An agent asking "how is the forecast computed?" or "what formula?" visits
// this single node to get the complete algorithm.
// ============================================================================

CREATE (:ForecastEngine {
  name: 'Construction Forecast Calculation Engine',

  purpose: 'Computes the Forecasted Construction Start Date for each site by walking the prerequisite dependency chain, computing planned dates, and consolidating tail milestones.',

  step_1_origin_date: 'Extract origin_date from the staging table column configured in gantt_config (default: pj_p_3710_ran_entitlement_complete_finish). This is the planned entitlement completion date. If NULL, the site cannot be computed.',

  step_2_planned_dates: 'Walk milestones in sort_order. For each: if root, ps=origin_date, pf=origin_date+expected_days. If dependent, ps=MAX(all predecessor planned_finishes)+start_gap_days, pf=ps+expected_days. Multi-dependency (e.g., 3850 depends on [3710,1327]): ps=MAX(pf_3710,pf_1327)+gap. Skipped milestones: expected_days=0, so pf=ps and downstream shifts earlier.',

  step_3_actual_extraction: 'For each milestone, extract actual completion from staging table using its column handler. Handlers: single=parse date column, max=MAX of multiple date columns, text=non-empty string means complete, with_status=status column controls skip/use_date/pending behavior.',

  step_4_milestone_status: 'For each milestone: if text handler and text populated -> On Track. If actual exists: delay=(actual-planned_finish).days; On Track if <=0, Delayed if >0. If no actual: remaining=(planned_finish-today).days; In Progress if >=0, Delayed if <0.',

  step_5_tail_consolidation: 'Identify tail milestones from prereq_tails table (3925+4d, steel+7d, 1555+5d, 4000+7d, 1407+7d). For each tail: effective_finish = planned_finish + offset_days. If tail is skipped, walk UP dependency chain to nearest non-skipped ancestor, use ancestor planned_finish + original offset. all_prereq_complete = MAX(all effective_finishes).',

  step_6_forecast: 'forecasted_cx_start = all_prereq_complete + CX_START_OFFSET_DAYS (default 4, from gantt_config table). This is the final output date.',

  step_7_site_status: 'Count milestones (excluding virtual and skipped). on_track_pct = (On Track count / total) * 100. Match against constraint_thresholds (type=milestone): first range containing pct determines status_label and color. Default: >=60% ON TRACK green, 30-59.99% IN PROGRESS orange, <30% CRITICAL red. If site is blocked (delay_comments or delay_code populated), status=BLOCKED regardless.',

  step_8_dashboard: 'Aggregate site statuses. on_track_pct = (ON TRACK sites / non-blocked total) * 100. Match against constraint_thresholds (type=overall). Returns dashboard_status, counts by category.',

  sla_priority: 'expected_days can be overridden. Priority: user_override (user_expected_days table) > history_based (history_expected_days column) > default (expected_days column). Applied before Step 2.',

  history_sla_computation: 'For each milestone: history_expected_days = ROUND(AVG(milestone_actual - predecessor_actual)) across sites where both dates fall within [date_from, date_to]. Root milestones: 0. Text milestones: keep default. Text predecessor: walk UP chain to nearest date-based ancestor (e.g., SPO uses Quote actual since CPO is text).',

  skip_handling: 'Skipped milestones (admin global or user-level): expected_days=0 in planned date computation. Excluded from status counting. Dependency maps transparently connect through: if A->B(skipped)->C, displays as A->C. Tail skip: walk up to active ancestor for tail consolidation.',

  data_flow: 'Nokia DB (staging) provides actual dates and site info. Config DB provides milestone definitions, dependencies, thresholds, user preferences. Origin date from staging planned column. All computed values are ephemeral (not stored).'
});

// ============================================================================
// NODE 3: SITE ELIGIBILITY & FILTERING
// An agent asking "which sites are included?" or "how are sites filtered?"
// ============================================================================

CREATE (:SiteEligibility {
  name: 'Site Eligibility and Filtering Rules',

  purpose: 'Determines which sites from the Nokia database are included in forecast calculations and how users can further filter the results.',

  base_eligibility: 'Three mandatory conditions (ALL must be true): 1) smp_name = NTM (project type). 2) construction_gc is non-empty (vendor assigned). 3) pj_a_4225_construction_start_finish IS NULL (construction not started). Applied as base WHERE clause on all queries.',

  blocked_site_detection: 'A site is BLOCKED if pj_construction_start_delay_comments OR pj_construction_complete_delay_code is non-empty. Effect: overall_status forced to BLOCKED, on_track_pct = 0. Blocked sites counted in dashboard total but excluded from percentage calculations. Individual milestone statuses still computed but irrelevant to overall.',

  geographic_filters: 'Users can filter by: region (column: region), market (column: m_market), area (column: m_area), site_id (column: s_site_id), vendor (column: construction_gc). All are exact-match equality filters.',

  gate_check_filters: 'Two additional filters: 1) plan_type_include - por_plan_type IN specified list (e.g., [New Build, FOA]). 2) regional_dev_initiatives - por_regional_dev_initiatives ILIKE %pattern% (case-insensitive substring). Saved per-user in user_filters table.',

  filter_persistence: 'All user filters (geographic + gate checks) saved in user_filters table (Config DB) keyed by user_id. Automatically loaded when user_id is provided in API calls. Can be cleared via DELETE /user-filters/{user_id}.',

  filter_interaction: 'Filters narrow the site set BEFORE any milestone computation happens. No computation overhead for filtered-out sites.',

  data_source: 'All filter columns come from Nokia DB staging table: stg_ndpd_mbt_tmobile_macro_combined'
});

// ============================================================================
// NODE 4: STATUS & THRESHOLD SYSTEM
// An agent asking "why is this site critical?" or "how are statuses assigned?"
// ============================================================================

CREATE (:StatusSystem {
  name: 'Status Classification System',

  purpose: 'Three-tier status system: individual milestone status, site overall status, and portfolio dashboard status. Each tier has distinct logic.',

  tier_1_milestone_status: 'Per-milestone. Three values: On Track (completed on/before deadline or text field populated), In Progress (not yet due, no actual), Delayed (past deadline or completed late). Formula: if text and populated -> On Track. If actual: delay=(actual-planned_finish).days, On Track if <=0 else Delayed. If no actual: remaining=(planned_finish-today).days, In Progress if >=0 else Delayed.',

  tier_2_site_status: 'Per-site aggregate. on_track_pct = (On Track milestones / total countable milestones) * 100. Virtual milestones and skipped milestones excluded from count. Percentage matched against milestone-level constraint_thresholds. BLOCKED overrides everything if delay comments/code present.',

  tier_3_dashboard_status: 'Portfolio aggregate. on_track_pct = (ON TRACK sites / non-blocked sites) * 100. Matched against overall-level constraint_thresholds. Blocked sites in total count but excluded from percentage.',

  default_thresholds: 'Both milestone and overall levels default to: >=60% = ON TRACK (green), 30-59.99% = IN PROGRESS (orange), <30% = CRITICAL (red).',

  threshold_configuration: 'Stored in constraint_thresholds table (Config DB). Fields: constraint_type (milestone/overall), name, status_label, color, min_pct, max_pct (null=100), sort_order. Matching: walk in sort_order, first range containing pct wins. Fallback: IN PROGRESS / orange.',

  threshold_customization: 'CRUD via /constraints endpoints. Can add/modify/delete thresholds. Example: add a WARNING tier at 40-59% by creating a new row. Changes affect all status computations immediately.',

  delay_days_meaning: 'Negative = completed early by that many days. Zero = on time. Positive = completed late by that many days. Only computed when actual date exists.',

  days_remaining_meaning: 'Only shown for milestones not yet completed. (planned_finish - today).days. Negative means overdue.',

  days_since_meaning: 'Only shown for completed milestones. (today - actual).days. How long ago it was completed.'
});

// ============================================================================
// NODE 5: PLANNING & OPTIMIZATION
// An agent answering "when should prerequisites start for target date X?"
// or "which sites should this vendor prioritize?"
// ============================================================================

CREATE (:PlanningEngine {
  name: 'Planning and Optimization Capabilities',

  purpose: 'Supports forward forecasting, backward planning from target dates, vendor capacity optimization, and SLA-based schedule tuning.',

  forward_forecast: 'Given a site with an entitlement date, compute the earliest construction start date by walking the prerequisite chain forward. This is the standard forecast computation (see ForecastEngine node).',

  backward_planning: 'Given a TARGET construction start date: 1) all_prereq_complete = target - CX_START_OFFSET_DAYS (4d). 2) For each tail: required_finish = all_prereq_complete - tail_offset_days. 3) Walk chain backwards: for each milestone, required_finish = successor_start - start_gap_days, required_start = required_finish - expected_days. 4) Root required_start = when entitlement must be complete. FEASIBILITY: if any required_start is in the past, the target is not achievable with current SLAs.',

  vendor_capacity: 'Vendors have limits: max_daily_sites (default 5), max_concurrent_sites (default 50). Stored in vendor_capacity table (Config DB). Vendor assignment from construction_gc column (Nokia DB). Prioritization logic: rank sites by forecast date (earliest first), exclude blocked, prefer higher on_track_pct, select top N within limits.',

  sla_optimization: 'Three SLA sources with priority: user_override > history_based > default. User overrides: per-user per-milestone via user_expected_days table, set via PUT /user-expected-days/{user_id}. History-based: computed from AVG actual durations in a date range, set via GET /sla-history/gantt-charts?date_from=X&date_to=Y. Reset via POST /sla-history/reset. Default: milestone_definitions.expected_days.',

  what_if_scenarios: 'An agent can simulate: 1) Skip a prerequisite -> see how forecast improves (expected_days becomes 0). 2) Change SLA duration -> recompute planned dates with new expected_days. 3) Change target date -> backward plan to check feasibility. 4) Filter by vendor -> see which sites a specific vendor should prioritize.',

  critical_path_identification: 'The critical path is the longest chain from root to forecast. Typically: 3710->1310->site_walk->1323->1327->quote->cpo->1555->all_prereq->cx_forecast (~59d). To accelerate forecast, reduce expected_days on critical path milestones. Reducing non-critical milestones has no effect unless they become the new critical path.'
});

// ============================================================================
// NODE 6: DATA COLUMN REFERENCE
// An agent that needs to know "which column maps to which milestone?"
// or needs to write a query against the staging table.
// ============================================================================

CREATE (:DataReference {
  name: 'Data Sources and Column Mapping Reference',

  purpose: 'Reference for all database columns, tables, and data sources used in the forecast system. Consult this when you need exact column names for queries or data validation.',

  nokia_db: 'Database: nokia_bkg_sample. Table: stg_ndpd_mbt_tmobile_macro_combined (read-only staging from external pipeline).',

  config_db: 'Database: schedular_agent. Tables: milestone_definitions, milestone_columns, prereq_tails, gantt_config, constraint_thresholds, vendor_capacity, user_filters, user_skipped_prerequisites, user_expected_days, chat_history.',

  origin_date_column: 'pj_p_3710_ran_entitlement_complete_finish (configurable via gantt_config key PLANNED_START_COLUMN)',

  site_identity_columns: 's_site_id (site ID), pj_project_id (project ID), pj_project_name (project name)',

  geographic_columns: 'region, m_market (market), m_area (area)',

  vendor_column: 'construction_gc (GC assignment)',

  eligibility_columns: 'smp_name (must = NTM), construction_gc (must be non-empty), pj_a_4225_construction_start_finish (must be NULL)',

  blocked_columns: 'pj_construction_start_delay_comments, pj_construction_complete_delay_code (either non-empty = BLOCKED)',

  gate_check_columns: 'por_plan_type (IN list filter), por_regional_dev_initiatives (ILIKE pattern filter)',

  milestone_column_map: '3710: pj_a_3710_ran_entitlement_complete_finish (date). 1310: ms_1310_pre_construction_package_received_actual (date). site_walk: MAX(ms_1316_pre_con_site_walk_completed_actual, ms_1321_talon_view_drone_svcs_actual) (date+date). 1323: ms_1323_ready_for_scoping_actual (date). 1327: ms_1327_scoping_and_quoting_package_validated_actual (date). 3850: pj_a_3850_bom_submitted_bom_in_bat_finish (date). 3875: pj_a_3875_bom_received_bom_in_aims_finish (date). quote: ms_1331_scoping_package_submitted_actual (date). cpo: ms1555_construction_complete_so_header (text). 1555: ms1555_construction_complete_spo_issued_date (date). steel: pj_steel_received_date + pj_steel_received_status (date+status). 3925: pj_a_3925_msl_pickup_date_finish (date). 1407: ms_1407_tower_ntp_validated_actual (date). 4000: pj_a_4000_ll_ntp_received (text).',

  handler_types: 'single: parse one date column. max: MAX of multiple date columns. text: non-empty string = complete (On Track), empty = In Progress. with_status: status column controls behavior - skip values auto-complete, use_date values use date column, others = pending.',

  config_key_columns: 'milestone_definitions: key (unique ID), name, expected_days, depends_on (single key or JSON array), start_gap_days, task_owner, phase_type, is_skipped, history_expected_days. milestone_columns: milestone_key, column_name, column_role (date/text/status), logic (JSON). prereq_tails: milestone_key, offset_days. gantt_config: config_key, config_value.'
});

// ============================================================================
// RELATIONSHIPS: Connect the knowledge nodes
// ============================================================================

// PrerequisiteChain feeds into ForecastEngine
MATCH (chain:PrerequisiteChain), (engine:ForecastEngine)
CREATE (engine)-[:USES_CHAIN {description: 'Forecast engine walks this prerequisite chain to compute dates'}]->(chain);

// ForecastEngine produces statuses via StatusSystem
MATCH (engine:ForecastEngine), (status:StatusSystem)
CREATE (engine)-[:PRODUCES_STATUS {description: 'Milestone statuses computed during forecast feed into status classification'}]->(status);

// SiteEligibility filters sites before ForecastEngine runs
MATCH (eligibility:SiteEligibility), (engine:ForecastEngine)
CREATE (eligibility)-[:FILTERS_SITES_FOR {description: 'Only eligible and filtered sites enter the forecast computation'}]->(engine);

// PlanningEngine extends ForecastEngine with advanced scenarios
MATCH (planning:PlanningEngine), (engine:ForecastEngine)
CREATE (planning)-[:EXTENDS {description: 'Planning capabilities (backward planning, vendor capacity, SLA tuning) build on top of the forecast engine'}]->(engine);

// PlanningEngine uses PrerequisiteChain for backward planning
MATCH (planning:PlanningEngine), (chain:PrerequisiteChain)
CREATE (planning)-[:WALKS_BACKWARDS {description: 'Backward planning reverses the prerequisite chain from target date to required start dates'}]->(chain);

// DataReference supports all nodes
MATCH (ref:DataReference), (chain:PrerequisiteChain)
CREATE (chain)-[:COLUMN_DETAILS_IN {description: 'Exact column names and handlers for each milestone'}]->(ref);

MATCH (ref:DataReference), (eligibility:SiteEligibility)
CREATE (eligibility)-[:COLUMN_DETAILS_IN {description: 'Exact column names for eligibility and filter checks'}]->(ref);

MATCH (ref:DataReference), (engine:ForecastEngine)
CREATE (engine)-[:COLUMN_DETAILS_IN {description: 'Data source configuration details'}]->(ref);

// StatusSystem is configured via thresholds (self-contained description)
// PlanningEngine uses StatusSystem for prioritization
MATCH (planning:PlanningEngine), (status:StatusSystem)
CREATE (planning)-[:USES_STATUS {description: 'Vendor prioritization uses site status and on_track_pct'}]->(status);

// ============================================================================
// INDEXES
// ============================================================================

CREATE INDEX chain_name_idx IF NOT EXISTS FOR (n:PrerequisiteChain) ON (n.name);
CREATE INDEX engine_name_idx IF NOT EXISTS FOR (n:ForecastEngine) ON (n.name);
CREATE INDEX eligibility_name_idx IF NOT EXISTS FOR (n:SiteEligibility) ON (n.name);
CREATE INDEX status_name_idx IF NOT EXISTS FOR (n:StatusSystem) ON (n.name);
CREATE INDEX planning_name_idx IF NOT EXISTS FOR (n:PlanningEngine) ON (n.name);
CREATE INDEX ref_name_idx IF NOT EXISTS FOR (n:DataReference) ON (n.name);

// ============================================================================
// VERIFICATION
// ============================================================================

// Count nodes: MATCH (n) RETURN labels(n)[0] AS type, count(n) ORDER BY type;
// See all relationships: MATCH (a)-[r]->(b) RETURN labels(a)[0], type(r), labels(b)[0];
// Get full chain: MATCH (c:PrerequisiteChain) RETURN c.milestone_details;
// Get forecast algorithm: MATCH (e:ForecastEngine) RETURN e;
