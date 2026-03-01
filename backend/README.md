# Gantt Chart Backend

This is the backend for the Gantt Chart application, built with FastAPI and PostgreSQL.

## Prerequisites

- **Python 3.12**
- PostgreSQL (ensure it's running and you have the credentials)

## Getting Started

Follow these steps to set up and run the backend locally:

### 1. Project Structure
```text
backend/
├── app/
│   ├── main.py          # FastAPI entry point
│   ├── routers/         # API endpoints
│   ├── services/        # Business logic (gantt calculation)
│   │   └── gantt/
│   │       ├── milestones.py # Milestone definitions (days, dependencies, tails)
│   │       ├── logic.py     # Timeline calculation & status engine
│   │       ├── utils.py     # Date parsing helpers
│   │       ├── queries.py   # SQL query builder
│   │       └── service.py   # Orchestration & dashboard summary
│   ├── models/          # Database models
│   └── schemas/         # Pydantic schemas
├── requirements.txt     # Python dependencies
└── .env                 # Environment variables (Database URL, etc.)
```

### 2. Environment Setup
Create a virtual environment:
```bash
python3.12 -m venv venv
source venv/bin/activate
```

Install dependencies:
```bash
pip install -r requirements.txt
```

### 3. Database Configuration
Ensure your `.env` file contains the correct `DATABASE_URL`. Example:
```env
DATABASE_URL=postgresql://postgres:passwrd@localhost:5432/rebalance_physio
```

### 4. Running the Application
To start the FastAPI server with reload enabled:
```bash
python3.12 -m uvicorn app.main:app --reload
```
The API will be available at `http://localhost:8000`.

## Milestone Logic (`services/gantt/logic.py`)

The Gantt chart calculates planned dates for **14 milestones** based on dependency chains. All timelines originate from the **Entitlement Complete (MS 3710)** planned date.

### Dependency Flow

```text
Entitlement (3710) [0d] ─── origin
│
├── Pre-NTP [2d] (parallel from Entitlement)
│   └── Site Walk [7d]
│       └── Ready for Scoping (1323) [3d]
│           └── Scoping Validated (1327) [7d]
│               │
│               ├── Steel Received [14d]
│               │   └── Material Pickup (3925) [5d]
│               │
│               ├── Quote Submitted [7d]
│               │   └── CPO Available [14d]
│               │       └── SPO Issued [5d]
│               │
│               ├── Access Confirmation [7d] (parallel)
│               └── NTP Received [7d] (parallel)
│
├── BOM PATH (starts after BOTH Entitlement & Scoping Validated — max of both)
│   ├── BOM in BAT (3850) [2d]
│   └── BOM in AIMS (3875) [21d]
```

### All 14 Milestones

| # | Milestone | Duration | Depends On | Key |
|---|-----------|----------|------------|-----|
| 1 | Entitlement Complete (MS 3710) | 0d | — (origin) | `3710` |
| 2 | Pre-NTP Document Received | 2d | Entitlement Complete | `pre_ntp` |
| 3 | Site Walk Performed | 7d | Pre-NTP | `site_walk` |
| 4 | Ready for Scoping (MS 1323) | 3d | Site Walk | `1323` |
| 5 | Scoping Validated by GC (MS 1327) | 7d | Ready for Scoping | `1327` |
| 6 | BOM in BAT (MS 3850) | 14d | max(Entitlement, Scoping Validated) | `3850` |
| 7 | BOM Received in AIMS (MS 3875) | 21d | BOM in BAT | `3875` |
| 8 | Steel Received (If applicable) | 14d | **Scoping Validated** | `steel` |
| 9 | Material Pickup by GC (MS 3925) | 5d | Steel Received | `3925` |
| 10 | Quote Submitted to Customer | 7d | Scoping Validated | `quote` |
| 11 | CPO Available | 14d | Quote Submitted | `cpo` |
| 12 | SPO Issued | 5d | CPO Available | `spo` |
| 13 | Access Confirmation | 7d | Scoping Validated | `access` |
| 14 | NTP Received | 7d | Scoping Validated | `ntp` |
| 15 | All Prerequisites Complete | — | max of all tails | `all_prereq` |

### Steel Received Logic

Steel has 3 status values from the database (`a_steel_status`):

| Status | Meaning | Behavior |
|--------|---------|----------|
| `N` / blank | Not Applicable | Auto mark **On Track**, skip delay check |
| `A` | Actually Received | Use `a_steel_date` as actual finish, compute delay |
| `P` | Pending | No actual date, compute In Progress / Delayed vs today |

**Key Rules:**
- **BOM in BAT (3850)** depends on **both** Entitlement Complete (3710) **and** Scoping Validated (1327). It starts from whichever finishes **last** (`max(p_3710, pf_scoping_validated)`).
- **Steel Received** depends on **Scoping Validated (MS 1327)** and takes **14 days** after scoping validation completes.

### Status Calculation

Each milestone gets a status based on:
- **On Track** — actual finish exists and is on or before planned finish
- **In Progress** — no actual finish yet, but planned finish is still in the future
- **Delayed** — actual finish is after planned finish, OR planned finish has passed with no actual

### All Prerequisites Complete

The "All Prerequisites Complete" date is calculated by taking the **max** of these 5 tail finish dates (each with an additional offset):

| Tail Milestone | Offset After Finish |
|----------------|---------------------|
| Material Pickup (3925) | + 4 days |
| Steel Received | + 7 days |
| SPO Issued | + 5 days |
| Access Confirmation | + 7 days |
| NTP Received | + 7 days |

```
All Prerequisites Complete = max(pf_3925+4, pf_steel+7, pf_spo+5, pf_access+7, pf_ntp+7)
```

### Forecasted CX Start

```
Forecasted CX Start = All Prerequisites Complete + 4 days
```

### Overall Site Status

Based on the maximum delay across all milestones:

| Max Delay | Status |
|-----------|--------|
| >= 15 days | CRITICAL |
| >= 8 days | HIGH RISK |
| >= 1 day | DELAYED |
| 0 days (active) | IN PROGRESS |
| else | PENDING |

## Documentation
- **Swagger UI**: [http://localhost:8000/docs](http://localhost:8000/docs)
- **ReDoc**: [http://localhost:8000/redoc](http://localhost:8000/redoc)


