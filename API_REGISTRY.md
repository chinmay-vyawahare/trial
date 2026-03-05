# API Registry

Base: `/api/v1/schedular`

---

## Gantt Charts

### GET `/gantt-charts`

**Input (Query Params):**
```json
{
  "region": "string",
  "market": "string",
  "site_id": "string",
  "vendor": "string",
  "area": "string",
  "user_id": "string",
  "limit": "int",
  "offset": "int"
}
```

**Output:**
```json
{
  "count": "int",
  "sites": [
    {
      "site_id": "string",
      "project_id": "string",
      "project_name": "string",
      "market": "string",
      "region": "string",
      "construction_start_4225": "string | null",
      "gc_assignment": "string | null",
      "overall_status": "string",
      "overall_progress": "float",
      "critical_path_delay": "int",
      "milestones": [
        {
          "key": "string",
          "name": "string",
          "sort_order": "int",
          "path": "string",
          "expected_days": "int",
          "dependency_type": "string",
          "task_owner": "string | null",
          "phase_type": "string | null",
          "preceding_milestones": ["string"],
          "following_milestones": ["string"],
          "planned_start": "string | null",
          "planned_finish": "string | null",
          "actual_finish": "string | null",
          "actual_value": "string | null",
          "days_since": "int | null",
          "days_remaining": "int | null",
          "delay_days": "int | null",
          "status": "string",
        }
      ]
    }
  ],
  "pagination": {
    "limit": "int | null",
    "offset": "int | null",
    "total_count": "int"
  }
}
```

---

### GET `/gantt-charts/dashboard`

**Input (Query Params):**
```json
{
  "region": "string",
  "market": "string",
  "vendor": "string",
  "area": "string",
  "user_id": "string"
}
```

**Output:**
```json
{
  "dashboard_status": "string",
  "on_track_pct": "float",
  "total_sites": "int",
  "in_progress_sites": "int",
  "critical_sites": "int",
  "on_track_sites": "int"
}
```

---

## Filters

### GET `/filters/regions`
**Input:** None
**Output:** `["string"]`

### GET `/filters/markets`
**Input:** None
**Output:** `["string"]`

### GET `/filters/areas`
**Input:** None
**Output:** `["string"]`

### GET `/filters/sites`
**Input:** None
**Output:** `["string"]`

### GET `/filters/vendors`
**Input:** None
**Output:** `["string"]`

---

## Gate Checks

### GET `/gate-checks/por_plan_type`
**Input:** None
**Output:** `["string"]`

### GET `/gate-checks/por_regional_dev_initiatives`
**Input:** None
**Output:** `["string"]`

### POST `/gate-checks`

**Input (Body):**
```json
{
  "user_id": "string",
  "plan_type_include": ["string"] | null,
  "regional_dev_initiatives": "string | null"
}
```

**Output:**
```json
{
  "user_id": "string",
  "plan_type_include": ["string"] | null,
  "regional_dev_initiatives": "string | null"
}
```

### GET `/gate-checks/{user_id}`
**Input (Path):** `user_id: string`

**Output:**
```json
{
  "user_id": "string",
  "plan_type_include": ["string"] | null,
  "regional_dev_initiatives": "string | null"
}
```

---

## Prerequisites

### GET `/prerequisites`
**Input:** None

**Output:**
```json
[
  {
    "id": "int",
    "key": "string",
    "name": "string",
    "sort_order": "int",
    "expected_days": "int",
    "start_gap_days": "int",
    "task_owner": "string | null",
    "phase_type": "string | null",
    "preceding_milestones": ["string"],
    "following_milestones": ["string"]
  }
]
```

### GET `/prerequisites/{prerequisite_id}`
**Input (Path):** `prerequisite_id: int`
**Output:** Same as single item above

### PUT `/prerequisites/{prerequisite_id}`
**Input (Path):** `prerequisite_id: int`

**Input (Body — all optional):**
```json
{
  "name": "string",
  "expected_days": "int",
  "start_gap_days": "int",
  "task_owner": "string",
  "phase_type": "string"
}
```

**Output:** Same as single item above

---

## Constraints

### GET `/constraints`
**Input:** None

**Output:**
```json
[
  {
    "id": "int",
    "constraint_type": "string",
    "name": "string",
    "status_label": "string",
    "color": "string",
    "min_pct": "float",
    "max_pct": "float | null",
    "sort_order": "int"
  }
]
```

### GET `/constraints/milestone`
**Input:** None
**Output:** Same as above (filtered to milestone type)

### GET `/constraints/overall`
**Input:** None
**Output:** Same as above (filtered to overall type)

### GET `/constraints/{constraint_id}`
**Input (Path):** `constraint_id: int`
**Output:** Single item from above

### POST `/constraints`

**Input (Body):**
```json
{
  "constraint_type": "string",
  "name": "string",
  "status_label": "string",
  "color": "string",
  "min_pct": "float",
  "max_pct": "float | null",
  "sort_order": "int"
}
```

**Output:** Same as single item above (with `id`)

### PUT `/constraints/{constraint_id}`
**Input (Path):** `constraint_id: int`

**Input (Body — all optional):**
```json
{
  "name": "string",
  "status_label": "string",
  "color": "string",
  "min_pct": "float",
  "max_pct": "float",
  "sort_order": "int"
}
```

**Output:** Same as single item above

### DELETE `/constraints/{constraint_id}`
**Input (Path):** `constraint_id: int`

**Output:**
```json
{ "detail": "string" }
```

---

## User Filters

### POST `/user-filters`

**Input (Body):**
```json
{
  "user_id": "string",
  "region": "string | null",
  "market": "string | null",
  "vendor": "string | null",
  "site_id": "string | null",
  "area": "string | null",
  "plan_type_include": ["string"] | null,
  "regional_dev_initiatives": "string | null"
}
```

**Output:**
```json
{
  "id": "int",
  "user_id": "string",
  "region": "string | null",
  "market": "string | null",
  "vendor": "string | null",
  "site_id": "string | null",
  "area": "string | null",
  "plan_type_include": "string | null",
  "regional_dev_initiatives": "string | null"
}
```

### GET `/user-filters/{user_id}`
**Input (Path):** `user_id: string`
**Output:** Same as above

### DELETE `/user-filters/{user_id}`
**Input (Path):** `user_id: string`

**Output:**
```json
{ "detail": "string" }
```

---

## Health

### GET `/api/health`
**Input:** None

**Output:**
```json
{ "status": "string" }
```
