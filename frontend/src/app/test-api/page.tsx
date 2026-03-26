"use client";

import { useState, useCallback, useRef, useEffect } from "react";
import Link from "next/link";

/* ─────────────────────────────────────────────────────────────────────────────
   GENERIC, REUSABLE API TEST RUNNER

   To add a new backend, just update API_BASE_URL and TEST_SUITES below.
   Each test suite defines its endpoints and the filter combos to try.
   ──────────────────────────────────────────────────────────────────────────── */

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/* ── Filter combos to test with ──────────────────────────────────────────── */

interface FilterCombo {
  label: string;
  params: Record<string, string | string[]>;
}

interface EndpointDef {
  id: string;
  name: string;
  method: "GET" | "POST" | "PUT" | "DELETE";
  path: string;
  /** Static body for POST/PUT */
  body?: Record<string, unknown>;
  /** Which filter combos to use (indexes into FILTER_COMBOS, or "none") */
  filterMode: "geo" | "geo+dates" | "geo+sla_dates" | "none" | "user" | "calendar";
  /** Extra static params always appended */
  staticParams?: Record<string, string>;
  /** Whether this test needs a dynamic value fetched first */
  skip?: boolean;
}

interface TestSuite {
  name: string;
  color: string; // pastel bg class
  accentColor: string;
  iconBg: string;
  endpoints: EndpointDef[];
}

/* The actual filter combos we'll test each geo-filter endpoint with */
const GEO_FILTER_COMBOS: FilterCombo[] = [
  { label: "No filters", params: {} },
  { label: "region=WEST", params: { region: "WEST" } },
  { label: "region=[WEST,EAST]", params: { region: ["WEST", "EAST"] } },
  { label: "market=DALLAS", params: { market: "DALLAS" } },
  { label: "area=PLANO", params: { area: "PLANO" } },
  { label: "multi: region+market", params: { region: "WEST", market: "DALLAS" } },
];

const SLA_DATE_COMBOS: FilterCombo[] = [
  { label: "SLA dates", params: { date_from: "2024-01-01", date_to: "2025-12-31" } },
  { label: "SLA + region", params: { date_from: "2024-01-01", date_to: "2025-12-31", region: "WEST" } },
];

const CALENDAR_COMBOS: FilterCombo[] = [
  { label: "30-day range", params: { start_date: "2025-01-01", end_date: "2025-01-31" } },
  { label: "range + region", params: { start_date: "2025-01-01", end_date: "2025-06-30", region: "WEST" } },
];

const CX_DATE_COMBOS: FilterCombo[] = [
  { label: "No dates", params: {} },
  { label: "With dates", params: { start_date: "2024-01-01", end_date: "2025-12-31" } },
  { label: "Dates + region", params: { start_date: "2024-01-01", end_date: "2025-12-31", region: "WEST" } },
];

/* ── Test Suite Definitions ──────────────────────────────────────────────── */

const TEST_SUITES: TestSuite[] = [
  {
    name: "Health & Filters",
    color: "bg-emerald-50",
    accentColor: "text-emerald-700",
    iconBg: "bg-emerald-100",
    endpoints: [
      { id: "health", name: "Health Check", method: "GET", path: "/api/health", filterMode: "none" },
      { id: "filter-regions", name: "Filter: Regions", method: "GET", path: "/api/v1/schedular/filters/regions", filterMode: "none" },
      { id: "filter-markets", name: "Filter: Markets", method: "GET", path: "/api/v1/schedular/filters/markets", filterMode: "none" },
      { id: "filter-areas", name: "Filter: Areas", method: "GET", path: "/api/v1/schedular/filters/areas", filterMode: "none" },
      { id: "filter-sites", name: "Filter: Sites", method: "GET", path: "/api/v1/schedular/filters/sites", filterMode: "none" },
      { id: "filter-vendors", name: "Filter: Vendors", method: "GET", path: "/api/v1/schedular/filters/vendors", filterMode: "none" },
    ],
  },
  {
    name: "Gantt Charts",
    color: "bg-blue-50",
    accentColor: "text-blue-700",
    iconBg: "bg-blue-100",
    endpoints: [
      { id: "gantt-default", name: "Gantt Charts (default SLA)", method: "GET", path: "/api/v1/schedular/gantt-charts", filterMode: "geo" },
    ],
  },
  {
    name: "Dashboard",
    color: "bg-violet-50",
    accentColor: "text-violet-700",
    iconBg: "bg-violet-100",
    endpoints: [
      { id: "dash-default", name: "Dashboard Summary (default)", method: "GET", path: "/api/v1/schedular/dashboard/sla-default-summary", filterMode: "geo" },
      { id: "dash-history", name: "Dashboard Summary (SLA history)", method: "GET", path: "/api/v1/schedular/dashboard/sla-history-summary", filterMode: "geo+sla_dates" },
      { id: "weekly-default", name: "Weekly Status (default)", method: "GET", path: "/api/v1/schedular/dashboard/weekly-status-sla-default", filterMode: "geo" },
      { id: "weekly-history", name: "Weekly Status (SLA history)", method: "GET", path: "/api/v1/schedular/dashboard/weekly-status-sla-history", filterMode: "geo+sla_dates" },
    ],
  },
  {
    name: "SLA History",
    color: "bg-amber-50",
    accentColor: "text-amber-700",
    iconBg: "bg-amber-100",
    endpoints: [
      { id: "sla-gantt", name: "SLA History Gantt", method: "GET", path: "/api/v1/schedular/sla-history/gantt-charts", filterMode: "geo+sla_dates" },
    ],
  },
  {
    name: "Analytics",
    color: "bg-rose-50",
    accentColor: "text-rose-700",
    iconBg: "bg-rose-100",
    endpoints: [
      { id: "pending-auto", name: "Pending Milestones (auto)", method: "GET", path: "/api/v1/schedular/analytics/pending-milestones/auto", filterMode: "geo" },
      { id: "pending-history", name: "Pending Milestones (SLA history)", method: "GET", path: "/api/v1/schedular/analytics/pending-milestones/sla-history", filterMode: "geo+sla_dates" },
      { id: "by-ms-auto", name: "Pending By Milestone (auto)", method: "GET", path: "/api/v1/schedular/analytics/pending-by-milestone/auto", filterMode: "geo" },
      { id: "by-ms-history", name: "Pending By Milestone (SLA history)", method: "GET", path: "/api/v1/schedular/analytics/pending-by-milestone/sla-history", filterMode: "geo+sla_dates" },
      { id: "drill-auto", name: "Drilldown (auto)", method: "GET", path: "/api/v1/schedular/analytics/drilldown/auto", filterMode: "geo", staticParams: { drilldown_type: "pending_count", pending_count: "0" } },
      { id: "drill-history", name: "Drilldown (SLA history)", method: "GET", path: "/api/v1/schedular/analytics/drilldown/sla-history", filterMode: "geo+sla_dates", staticParams: { drilldown_type: "pending_count", pending_count: "0" } },
    ],
  },
  {
    name: "CX Forecast & Actual",
    color: "bg-teal-50",
    accentColor: "text-teal-700",
    iconBg: "bg-teal-100",
    endpoints: [
      { id: "cx-forecast", name: "CX Forecast Summary", method: "GET", path: "/api/v1/schedular/cx-forecast-summary", filterMode: "geo+dates" },
      { id: "cx-actual", name: "CX Actual Summary", method: "GET", path: "/api/v1/schedular/cx-actual-summary", filterMode: "geo+dates" },
    ],
  },
  {
    name: "Calendar",
    color: "bg-sky-50",
    accentColor: "text-sky-700",
    iconBg: "bg-sky-100",
    endpoints: [
      { id: "calendar-default", name: "Calendar Sites", method: "GET", path: "/api/v1/schedular/calendar", filterMode: "calendar" },
      { id: "calendar-history", name: "Calendar History", method: "GET", path: "/api/v1/schedular/calendar/history", filterMode: "calendar", staticParams: { sla_date_from: "2024-01-01", sla_date_to: "2025-12-31" } },
    ],
  },
  {
    name: "Prerequisites & Constraints",
    color: "bg-indigo-50",
    accentColor: "text-indigo-700",
    iconBg: "bg-indigo-100",
    endpoints: [
      { id: "prereqs", name: "Prerequisites", method: "GET", path: "/api/v1/schedular/prerequisites", filterMode: "none" },
      { id: "prereq-flow", name: "Prerequisite Flowchart", method: "GET", path: "/api/v1/schedular/prerequisites/flowchart", filterMode: "none" },
      { id: "constraints-all", name: "All Constraints", method: "GET", path: "/api/v1/schedular/constraints", filterMode: "none" },
      { id: "constraints-ms", name: "Milestone Constraints", method: "GET", path: "/api/v1/schedular/constraints/milestone", filterMode: "none" },
      { id: "constraints-ov", name: "Overall Constraints", method: "GET", path: "/api/v1/schedular/constraints/overall", filterMode: "none" },
    ],
  },
  {
    name: "User & Admin",
    color: "bg-fuchsia-50",
    accentColor: "text-fuchsia-700",
    iconBg: "bg-fuchsia-100",
    endpoints: [
      { id: "user-expected", name: "User Expected Days", method: "GET", path: "/api/v1/schedular/user-expected-days/test_user", filterMode: "none" },
      { id: "user-filters", name: "User Filters", method: "GET", path: "/api/v1/schedular/user-filters/test_user", filterMode: "none" },
      { id: "gate-plan", name: "Gate Check: Plan Types", method: "GET", path: "/api/v1/schedular/gate-checks/por_plan_type", filterMode: "none" },
      { id: "gate-dev", name: "Gate Check: Dev Initiatives", method: "GET", path: "/api/v1/schedular/gate-checks/por_regional_dev_initiatives", filterMode: "none" },
      { id: "gc-capacity", name: "GC Capacity", method: "GET", path: "/api/v1/schedular/gc-capacity", filterMode: "none" },
      { id: "pace-geo", name: "Pace Constraints: Geo Hierarchy", method: "GET", path: "/api/v1/schedular/pace-constraints/geo-hierarchy", filterMode: "none" },
      { id: "admin-skip", name: "Admin: Skipped Prerequisites", method: "GET", path: "/api/v1/schedular/admin/skip-prerequisites", filterMode: "none" },
      { id: "admin-staging", name: "Admin: Staging Columns", method: "GET", path: "/api/v1/schedular/admin/staging-columns", filterMode: "none" },
      { id: "history-sla", name: "History SLA Days (reset)", method: "POST", path: "/api/v1/schedular/history-sla-days/reset", filterMode: "none" },
    ],
  },
  {
    name: "Export (download check)",
    color: "bg-orange-50",
    accentColor: "text-orange-700",
    iconBg: "bg-orange-100",
    endpoints: [
      { id: "export-csv", name: "Export Gantt CSV", method: "GET", path: "/api/v1/schedular/export/gantt-csv", filterMode: "geo" },
      { id: "export-csv-hist", name: "Export Gantt CSV (history)", method: "GET", path: "/api/v1/schedular/export/gantt-csv-history", filterMode: "geo+sla_dates" },
    ],
  },
];

/* ── Types ──────────────────────────────────────────────────────────────── */

type TestStatus = "idle" | "running" | "pass" | "fail" | "warn";

interface TestResult {
  endpointId: string;
  comboLabel: string;
  status: TestStatus;
  statusCode?: number;
  responseTime?: number;
  responsePreview?: string;
  error?: string;
}

/* ── Helpers ─────────────────────────────────────────────────────────────── */

function buildUrl(path: string, params: Record<string, string | string[]>, staticParams?: Record<string, string>): string {
  const sp = new URLSearchParams();
  if (staticParams) {
    for (const [k, v] of Object.entries(staticParams)) sp.append(k, v);
  }
  for (const [k, v] of Object.entries(params)) {
    if (Array.isArray(v)) {
      for (const item of v) sp.append(k, item);
    } else {
      sp.append(k, v);
    }
  }
  const qs = sp.toString();
  return `${API_BASE_URL}${path}${qs ? `?${qs}` : ""}`;
}

function getCombosForMode(mode: EndpointDef["filterMode"]): FilterCombo[] {
  switch (mode) {
    case "geo": return GEO_FILTER_COMBOS;
    case "geo+dates": return CX_DATE_COMBOS;
    case "geo+sla_dates": return SLA_DATE_COMBOS;
    case "calendar": return CALENDAR_COMBOS;
    case "user": return [{ label: "user_id=test_user", params: { user_id: "test_user" } }];
    case "none": return [{ label: "No params", params: {} }];
    default: return [{ label: "No params", params: {} }];
  }
}

function truncate(s: string, max: number) {
  return s.length > max ? s.slice(0, max) + "..." : s;
}

/* ── Page Component ─────────────────────────────────────────────────────── */

export default function TestApiPage() {
  const [results, setResults] = useState<Map<string, TestResult>>(new Map());
  const [running, setRunning] = useState(false);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [expandedResults, setExpandedResults] = useState<Set<string>>(new Set());
  const [customBaseUrl, setCustomBaseUrl] = useState(API_BASE_URL);
  const abortRef = useRef<AbortController | null>(null);
  const [startTime, setStartTime] = useState<number | null>(null);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (!running || !startTime) return;
    const timer = setInterval(() => setElapsed(Date.now() - startTime), 200);
    return () => clearInterval(timer);
  }, [running, startTime]);

  const totalTests = TEST_SUITES.reduce((acc, s) => {
    return acc + s.endpoints.reduce((a, ep) => a + getCombosForMode(ep.filterMode).length, 0);
  }, 0);

  const runAllTests = useCallback(async () => {
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setRunning(true);
    setResults(new Map());
    setProgress({ done: 0, total: totalTests });
    setStartTime(Date.now());
    setElapsed(0);

    let done = 0;
    const newResults = new Map<string, TestResult>();

    for (const suite of TEST_SUITES) {
      for (const ep of suite.endpoints) {
        if (ep.skip) continue;
        const combos = getCombosForMode(ep.filterMode);

        for (const combo of combos) {
          if (ctrl.signal.aborted) break;

          const key = `${ep.id}::${combo.label}`;
          const baseUrl = customBaseUrl || API_BASE_URL;
          const url = buildUrl(ep.path, combo.params, ep.staticParams).replace(API_BASE_URL, baseUrl);

          newResults.set(key, { endpointId: ep.id, comboLabel: combo.label, status: "running" });
          setResults(new Map(newResults));

          const t0 = performance.now();
          try {
            const res = await fetch(url, {
              method: ep.method,
              signal: ctrl.signal,
              cache: "no-store",
              headers: ep.body ? { "Content-Type": "application/json" } : undefined,
              body: ep.body ? JSON.stringify(ep.body) : undefined,
            });
            const elapsed = Math.round(performance.now() - t0);

            let preview = "";
            try {
              const text = await res.text();
              preview = truncate(text, 300);
            } catch { /* ignore */ }

            newResults.set(key, {
              endpointId: ep.id,
              comboLabel: combo.label,
              status: res.ok ? "pass" : (res.status < 500 ? "warn" : "fail"),
              statusCode: res.status,
              responseTime: elapsed,
              responsePreview: preview,
              error: res.ok ? undefined : `HTTP ${res.status}`,
            });
          } catch (e: unknown) {
            if (ctrl.signal.aborted) break;
            const elapsed = Math.round(performance.now() - t0);
            newResults.set(key, {
              endpointId: ep.id,
              comboLabel: combo.label,
              status: "fail",
              responseTime: elapsed,
              error: e instanceof Error ? e.message : "Network error",
            });
          }

          done++;
          setProgress({ done, total: totalTests });
          setResults(new Map(newResults));
        }
      }
      if (ctrl.signal.aborted) break;
    }

    setRunning(false);
  }, [totalTests, customBaseUrl]);

  const stopTests = useCallback(() => {
    abortRef.current?.abort();
    setRunning(false);
  }, []);

  /* ── Stats ─────────────────────────────────────────────────────────── */
  const allResults = Array.from(results.values());
  const passed = allResults.filter((r) => r.status === "pass").length;
  const failed = allResults.filter((r) => r.status === "fail").length;
  const warned = allResults.filter((r) => r.status === "warn").length;
  const avgTime = allResults.length > 0
    ? Math.round(allResults.reduce((a, r) => a + (r.responseTime || 0), 0) / allResults.length)
    : 0;

  function toggleExpand(key: string) {
    setExpandedResults((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-violet-50">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-white/80 backdrop-blur-xl border-b border-gray-200 shadow-sm">
        <div className="max-w-7xl mx-auto px-6 py-4 flex items-center justify-between">
          <div className="flex items-center gap-4">
            <Link href="/" className="text-sm text-gray-400 hover:text-gray-600 transition-colors">
              &larr; Dashboard
            </Link>
            <div className="w-px h-6 bg-gray-200" />
            <div>
              <h1 className="text-lg font-bold text-gray-800">API Test Runner</h1>
              <p className="text-xs text-gray-400">{totalTests} tests across {TEST_SUITES.length} suites</p>
            </div>
          </div>
          <div className="flex items-center gap-3">
            <div className="flex flex-col">
              <label className="text-[9px] font-bold uppercase text-gray-400 mb-0.5">Base URL</label>
              <input
                type="text"
                value={customBaseUrl}
                onChange={(e) => setCustomBaseUrl(e.target.value)}
                disabled={running}
                className="px-3 py-1.5 text-xs rounded-lg border border-gray-200 bg-white text-gray-700 w-72 focus:outline-none focus:ring-2 focus:ring-blue-400 disabled:opacity-50"
              />
            </div>
            {running ? (
              <button
                onClick={stopTests}
                className="px-5 py-2 text-sm font-bold rounded-xl bg-red-500 text-white hover:bg-red-600 shadow-md transition-all"
              >
                Stop
              </button>
            ) : (
              <button
                onClick={runAllTests}
                className="px-5 py-2 text-sm font-bold rounded-xl bg-gradient-to-r from-blue-500 to-violet-500 text-white hover:from-blue-600 hover:to-violet-600 shadow-md transition-all"
              >
                Run All Tests
              </button>
            )}
          </div>
        </div>
      </header>

      <div className="max-w-7xl mx-auto px-6 py-6 space-y-6">
        {/* Progress bar + stats */}
        {(running || allResults.length > 0) && (
          <div className="bg-white rounded-2xl border border-gray-200 shadow-sm p-5">
            {/* Progress bar */}
            <div className="flex items-center gap-4 mb-4">
              <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full rounded-full transition-all duration-300 bg-gradient-to-r from-blue-400 to-violet-400"
                  style={{ width: `${progress.total > 0 ? (progress.done / progress.total) * 100 : 0}%` }}
                />
              </div>
              <span className="text-xs font-bold text-gray-500 tabular-nums w-20 text-right">
                {progress.done}/{progress.total}
              </span>
              {running && (
                <span className="text-xs text-gray-400 tabular-nums">{(elapsed / 1000).toFixed(1)}s</span>
              )}
            </div>

            {/* Stat cards */}
            <div className="grid grid-cols-5 gap-3">
              <div className="bg-emerald-50 rounded-xl p-3 text-center border border-emerald-100">
                <div className="text-2xl font-extrabold text-emerald-600">{passed}</div>
                <div className="text-[10px] font-bold uppercase text-emerald-500 mt-0.5">Passed</div>
              </div>
              <div className="bg-red-50 rounded-xl p-3 text-center border border-red-100">
                <div className="text-2xl font-extrabold text-red-600">{failed}</div>
                <div className="text-[10px] font-bold uppercase text-red-500 mt-0.5">Failed</div>
              </div>
              <div className="bg-amber-50 rounded-xl p-3 text-center border border-amber-100">
                <div className="text-2xl font-extrabold text-amber-600">{warned}</div>
                <div className="text-[10px] font-bold uppercase text-amber-500 mt-0.5">Warnings</div>
              </div>
              <div className="bg-blue-50 rounded-xl p-3 text-center border border-blue-100">
                <div className="text-2xl font-extrabold text-blue-600">{avgTime}ms</div>
                <div className="text-[10px] font-bold uppercase text-blue-500 mt-0.5">Avg Response</div>
              </div>
              <div className="bg-violet-50 rounded-xl p-3 text-center border border-violet-100">
                <div className="text-2xl font-extrabold text-violet-600">
                  {!running && allResults.length > 0 ? (elapsed / 1000).toFixed(1) + "s" : running ? "..." : "--"}
                </div>
                <div className="text-[10px] font-bold uppercase text-violet-500 mt-0.5">Total Time</div>
              </div>
            </div>
          </div>
        )}

        {/* Test suites */}
        {TEST_SUITES.map((suite) => {
          const suiteResults = allResults.filter((r) =>
            suite.endpoints.some((ep) => ep.id === r.endpointId)
          );
          const suitePassed = suiteResults.filter((r) => r.status === "pass").length;
          const suiteFailed = suiteResults.filter((r) => r.status === "fail").length;
          const suiteWarned = suiteResults.filter((r) => r.status === "warn").length;
          const suiteTotal = suite.endpoints.reduce((a, ep) => a + getCombosForMode(ep.filterMode).length, 0);
          const suiteRunning = suiteResults.some((r) => r.status === "running");

          return (
            <div key={suite.name} className={`${suite.color} rounded-2xl border border-gray-200/60 shadow-sm overflow-hidden`}>
              {/* Suite header */}
              <div className="px-5 py-3.5 flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div className={`w-8 h-8 rounded-lg ${suite.iconBg} flex items-center justify-center`}>
                    {suiteRunning ? (
                      <div className="w-4 h-4 border-2 border-current border-t-transparent rounded-full animate-spin opacity-60" />
                    ) : suiteFailed > 0 ? (
                      <span className="text-red-500 text-sm font-bold">!</span>
                    ) : suiteResults.length >= suiteTotal && suiteTotal > 0 ? (
                      <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" /></svg>
                    ) : (
                      <span className={`text-sm font-bold ${suite.accentColor} opacity-50`}>#</span>
                    )}
                  </div>
                  <div>
                    <h2 className={`text-sm font-bold ${suite.accentColor}`}>{suite.name}</h2>
                    <p className="text-[10px] text-gray-400">{suite.endpoints.length} endpoints, {suiteTotal} tests</p>
                  </div>
                </div>
                {suiteResults.length > 0 && (
                  <div className="flex items-center gap-2 text-[10px] font-bold">
                    {suitePassed > 0 && <span className="px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700">{suitePassed} passed</span>}
                    {suiteFailed > 0 && <span className="px-2 py-0.5 rounded-full bg-red-100 text-red-700">{suiteFailed} failed</span>}
                    {suiteWarned > 0 && <span className="px-2 py-0.5 rounded-full bg-amber-100 text-amber-700">{suiteWarned} warn</span>}
                  </div>
                )}
              </div>

              {/* Endpoints */}
              <div className="px-3 pb-3 space-y-1.5">
                {suite.endpoints.map((ep) => {
                  const combos = getCombosForMode(ep.filterMode);
                  const epResults = combos.map((c) => {
                    const key = `${ep.id}::${c.label}`;
                    return { key, combo: c, result: results.get(key) };
                  });

                  return (
                    <div key={ep.id} className="bg-white/70 rounded-xl border border-gray-200/40 overflow-hidden">
                      {/* Endpoint name + mini status row */}
                      <div className="px-4 py-2.5 flex items-center justify-between">
                        <div className="flex items-center gap-2.5">
                          <span className={`px-2 py-0.5 text-[9px] font-bold rounded-md ${
                            ep.method === "GET" ? "bg-blue-100 text-blue-600" :
                            ep.method === "POST" ? "bg-emerald-100 text-emerald-600" :
                            ep.method === "PUT" ? "bg-amber-100 text-amber-600" :
                            "bg-red-100 text-red-600"
                          }`}>
                            {ep.method}
                          </span>
                          <span className="text-xs font-semibold text-gray-700">{ep.name}</span>
                          <span className="text-[10px] text-gray-400 font-mono">{ep.path}</span>
                        </div>
                        {/* Mini status dots */}
                        <div className="flex items-center gap-1">
                          {epResults.map(({ key, result }) => (
                            <button
                              key={key}
                              onClick={() => toggleExpand(key)}
                              title={`${key}`}
                              className={`w-5 h-5 rounded-md flex items-center justify-center text-[10px] font-bold transition-all ${
                                !result || result.status === "idle"
                                  ? "bg-gray-100 text-gray-300"
                                  : result.status === "running"
                                  ? "bg-blue-100 text-blue-400 animate-pulse"
                                  : result.status === "pass"
                                  ? "bg-emerald-100 text-emerald-600 hover:bg-emerald-200"
                                  : result.status === "warn"
                                  ? "bg-amber-100 text-amber-600 hover:bg-amber-200"
                                  : "bg-red-100 text-red-600 hover:bg-red-200"
                              }`}
                            >
                              {!result || result.status === "idle" ? "·" :
                               result.status === "running" ? "~" :
                               result.status === "pass" ? "\u2713" :
                               result.status === "warn" ? "!" : "\u2717"}
                            </button>
                          ))}
                        </div>
                      </div>

                      {/* Expanded results */}
                      {epResults.some(({ key }) => expandedResults.has(key)) && (
                        <div className="border-t border-gray-100 px-4 py-2 space-y-1.5 bg-gray-50/50">
                          {epResults.filter(({ key }) => expandedResults.has(key)).map(({ key, combo, result }) => (
                            <div key={key} className="rounded-lg border border-gray-200 bg-white p-3">
                              <div className="flex items-center justify-between mb-1.5">
                                <div className="flex items-center gap-2">
                                  <span className="text-[10px] font-bold text-gray-500">{combo.label}</span>
                                  {result?.statusCode && (
                                    <span className={`px-1.5 py-0.5 text-[9px] font-bold rounded ${
                                      result.statusCode < 300 ? "bg-emerald-100 text-emerald-700" :
                                      result.statusCode < 500 ? "bg-amber-100 text-amber-700" :
                                      "bg-red-100 text-red-700"
                                    }`}>
                                      {result.statusCode}
                                    </span>
                                  )}
                                  {result?.responseTime !== undefined && (
                                    <span className="text-[10px] text-gray-400">{result.responseTime}ms</span>
                                  )}
                                </div>
                                <button onClick={() => toggleExpand(key)} className="text-[10px] text-gray-400 hover:text-gray-600">Close</button>
                              </div>
                              {result?.error && (
                                <div className="text-[10px] text-red-500 font-medium mb-1">{result.error}</div>
                              )}
                              {result?.responsePreview && (
                                <pre className="text-[10px] text-gray-500 font-mono bg-gray-50 rounded-md p-2 overflow-auto max-h-32 whitespace-pre-wrap break-all">
                                  {result.responsePreview}
                                </pre>
                              )}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
