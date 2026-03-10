"use client";

import { SiteGantt, Milestone } from "@/lib/types";
import { useMemo, useRef, useEffect, useState, useCallback } from "react";
import {
  parseISO,
  differenceInDays,
  addDays,
  eachDayOfInterval,
  eachWeekOfInterval,
  eachMonthOfInterval,
  format,
  startOfQuarter,
  addMonths,
} from "date-fns";
import type { TimelineView } from "./TabBar";

interface Props {
  sites: SiteGantt[];
  vendorNames: string[];
  expandedSites: Set<string>;
  expandedVendors: Set<string>;
  onToggleSite: (siteId: string) => void;
  onToggleVendor: (vendorName: string) => void;
  timelineView: TimelineView;
}

const ROW_H = 36;
const HEADER_H = 38;
const LABEL_W = 360;

function getColumnWidth(view: TimelineView): number {
  switch (view) {
    case "day": return 28;
    case "week": return 56;
    case "month": return 110;
    case "quarter": return 160;
    case "year": return 220;
  }
}

function getTimelineColumns(start: Date, end: Date, view: TimelineView): { date: Date; label: string; sub?: string }[] {
  switch (view) {
    case "day":
      return eachDayOfInterval({ start, end }).map((d) => ({
        date: d,
        label: format(d, "dd"),
        sub: format(d, "EEE"),
      }));
    case "week":
      return eachWeekOfInterval({ start, end }).map((d) => ({
        date: d,
        label: format(d, "MMM dd"),
      }));
    case "month":
      return eachMonthOfInterval({ start, end }).map((d) => ({
        date: d,
        label: format(d, "MMM yyyy"),
      }));
    case "quarter": {
      const cols: { date: Date; label: string }[] = [];
      let d = startOfQuarter(start);
      while (d <= end) {
        const q = Math.ceil((d.getMonth() + 1) / 3);
        cols.push({ date: d, label: `Q${q} ${format(d, "yyyy")}` });
        d = addMonths(d, 3);
      }
      return cols;
    }
    case "year": {
      const cols: { date: Date; label: string }[] = [];
      let y = start.getFullYear();
      while (y <= end.getFullYear()) {
        cols.push({ date: new Date(y, 0, 1), label: String(y) });
        y++;
      }
      return cols;
    }
  }
}

function getStatusBadge(status: string) {
  const s = status.toUpperCase();
  if (s === "CRITICAL")
    return { label: "Critical", cls: "bg-red-100 text-red-700 border-red-300" };
  if (s === "BLOCKED")
    return { label: "Blocked", cls: "bg-red-100 text-red-700 border-red-300" };
  if (s === "EXCLUDED - CREW SHORTAGE")
    return { label: "Excluded - Crew Shortage", cls: "bg-orange-100 text-orange-700 border-orange-300" };
  if (s === "EXCLUDED - PACE CONSTRAINT")
    return { label: "Excluded - Pace Constraint", cls: "bg-purple-100 text-purple-700 border-purple-300" };
  if (s === "IN PROGRESS")
    return { label: "In Progress", cls: "bg-amber-100 text-amber-700 border-amber-300" };
  if (s === "ON TRACK")
    return { label: "On Track", cls: "bg-emerald-100 text-emerald-700 border-emerald-300" };
  return { label: status || "Pending", cls: "bg-gray-100 text-gray-500 border-gray-300" };
}

function getBarColor(m: Milestone): string {
  if (m.status === "On Track") return "#22c55e";      // green
  if (m.status === "In Progress") return "#eab308";    // yellow
  if (m.status === "Delayed") return "#ef4444";        // red
  return "#cbd5e1";
}

function getMilestoneName(m: Milestone): string {
  return m.name || m.key;
}

type Row =
  | { type: "vendor"; vendorName: string; siteCount: number; delayedCount: number }
  | { type: "site"; site: SiteGantt }
  | { type: "ms"; site: SiteGantt; milestone: Milestone };

export default function GanttView({
  sites,
  vendorNames,
  expandedSites,
  expandedVendors,
  onToggleSite,
  onToggleVendor,
  timelineView,
}: Props) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const labelRef = useRef<HTMLDivElement>(null);
  const [labelWidth, setLabelWidth] = useState(LABEL_W);
  const isDragging = useRef(false);

  const onDragStart = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    isDragging.current = true;
    const startX = e.clientX;
    const startW = labelWidth;
    const onMove = (ev: MouseEvent) => {
      if (!isDragging.current) return;
      const newW = Math.max(200, Math.min(800, startW + ev.clientX - startX));
      setLabelWidth(newW);
    };
    const onUp = () => {
      isDragging.current = false;
      document.removeEventListener("mousemove", onMove);
      document.removeEventListener("mouseup", onUp);
      document.body.style.cursor = "";
      document.body.style.userSelect = "";
    };
    document.addEventListener("mousemove", onMove);
    document.addEventListener("mouseup", onUp);
    document.body.style.cursor = "col-resize";
    document.body.style.userSelect = "none";
  }, [labelWidth]);

  // Sync vertical scroll between labels and chart (bidirectional)
  useEffect(() => {
    const scrollEl = scrollRef.current;
    const labelEl = labelRef.current;
    if (!scrollEl || !labelEl) return;
    let syncing = false;
    const onChartScroll = () => {
      if (syncing) return;
      syncing = true;
      labelEl.scrollTop = scrollEl.scrollTop;
      syncing = false;
    };
    const onLabelScroll = () => {
      if (syncing) return;
      syncing = true;
      scrollEl.scrollTop = labelEl.scrollTop;
      syncing = false;
    };
    scrollEl.addEventListener("scroll", onChartScroll);
    labelEl.addEventListener("scroll", onLabelScroll);
    return () => {
      scrollEl.removeEventListener("scroll", onChartScroll);
      labelEl.removeEventListener("scroll", onLabelScroll);
    };
  }, []);

  // Group sites by vendor name
  const sitesByVendor = useMemo(() => {
    const map = new Map<string, SiteGantt[]>();
    for (const vn of vendorNames) map.set(vn, []);
    for (const s of sites) {
      const vn = s.vendor_name || "Unassigned";
      const arr = map.get(vn);
      if (arr) arr.push(s);
    }
    return map;
  }, [sites, vendorNames]);

  const { rangeStart, rangeEnd } = useMemo(() => {
    let minD: Date | null = null;
    let maxD: Date | null = null;
    for (const site of sites) {
      for (const m of site.milestones) {
        for (const d of [m.planned_start, m.planned_finish, m.actual_finish]) {
          if (d && /^\d{4}-\d{2}-\d{2}/.test(d)) {
            const dt = parseISO(d);
            if (!minD || dt < minD) minD = dt;
            if (!maxD || dt > maxD) maxD = dt;
          }
        }
      }
    }
    if (!minD) minD = new Date();
    if (!maxD) maxD = addDays(new Date(), 180);
    return { rangeStart: addDays(minD, -14), rangeEnd: addDays(maxD, 14) };
  }, [sites]);

  const colW = getColumnWidth(timelineView);
  const columns = useMemo(() => getTimelineColumns(rangeStart, rangeEnd, timelineView), [rangeStart, rangeEnd, timelineView]);
  const totalDays = differenceInDays(rangeEnd, rangeStart) || 1;
  const chartW = columns.length * colW;

  function dateToColIndex(d: string | null): number | null {
    if (!d || !/^\d{4}-\d{2}-\d{2}/.test(d)) return null;
    const dt = parseISO(d);
    let colIdx = 0;
    for (let i = columns.length - 1; i >= 0; i--) {
      if (dt >= columns[i].date) {
        colIdx = i;
        break;
      }
    }
    return colIdx;
  }

  const todayX = (differenceInDays(new Date(), rangeStart) / totalDays) * chartW;

  // Build rows: vendor > site > milestone hierarchy
  const rows: Row[] = [];
  for (const vendorName of vendorNames) {
    const vendorSites = sitesByVendor.get(vendorName) || [];
    const delayedCount = vendorSites.filter(
      (s) => {
        const st = s.overall_status.toUpperCase();
        return st === "CRITICAL" || st === "BLOCKED" || st === "EXCLUDED - CREW SHORTAGE" || st === "EXCLUDED - PACE CONSTRAINT";
      }
    ).length;
    rows.push({ type: "vendor", vendorName, siteCount: vendorSites.length, delayedCount });
    if (expandedVendors.has(vendorName)) {
      for (const site of vendorSites) {
        rows.push({ type: "site", site });
        if (expandedSites.has(site.site_id)) {
          for (const m of [...site.milestones].sort((a, b) => a.sort_order - b.sort_order)) {
            rows.push({ type: "ms", site, milestone: m });
          }
        }
      }
    }
  }

  return (
    <div className="flex h-full overflow-hidden border-t border-gray-200">
      {/* LEFT: Labels */}
      <div
        ref={labelRef}
        className="flex-shrink-0 overflow-auto bg-white"
        style={{ width: labelWidth }}
      >
        {/* Header */}
        <div className="sticky top-0 z-10 flex items-center px-3 border-b border-gray-200 bg-gray-50" style={{ height: HEADER_H, minWidth: 520 }}>
          <span className="text-[11px] font-bold tracking-wider uppercase text-gray-400">
            Vendor / Site / Task
          </span>
        </div>

        {/* Rows */}
        <div style={{ minWidth: 520 }}>
          {rows.map((row, idx) => {
            if (row.type === "vendor") {
              const expanded = expandedVendors.has(row.vendorName);
              const delayedPct = row.siteCount > 0
                ? Math.round((row.delayedCount / row.siteCount) * 100)
                : 0;
              return (
                <div
                  key={`l-v-${row.vendorName}`}
                  onClick={() => onToggleVendor(row.vendorName)}
                  className="flex items-center gap-2 px-3 cursor-pointer border-b border-gray-200 hover:bg-indigo-50 transition-colors"
                  style={{ height: ROW_H, background: "#e0e7ff" }}
                >
                  <span className="text-[10px] text-indigo-500 w-3 flex-shrink-0">
                    {expanded ? "▼" : "▶"}
                  </span>
                  <span className="text-xs font-bold text-indigo-800 whitespace-nowrap truncate">
                    {row.vendorName}
                  </span>
                  <span className="text-[10px] text-indigo-400 whitespace-nowrap ml-auto">
                    {row.siteCount} sites
                  </span>
                  {row.delayedCount > 0 && (
                    <span className="text-[9px] font-bold px-1.5 py-0.5 rounded-full border bg-red-50 text-red-600 border-red-200 whitespace-nowrap">
                      {row.delayedCount} delayed ({delayedPct}%)
                    </span>
                  )}
                </div>
              );
            }

            if (row.type === "site") {
              const s = row.site;
              const badge = getStatusBadge(s.overall_status);
              const expanded = expandedSites.has(s.site_id);
              return (
                <div
                  key={`l-s-${s.site_id}`}
                  onClick={() => onToggleSite(s.site_id)}
                  className="flex items-center gap-2 px-3 pl-6 cursor-pointer border-b border-gray-100 hover:bg-blue-50 transition-colors"
                  style={{ height: ROW_H, background: "#f0f4ff" }}
                >
                  <span className="text-[10px] text-gray-400 w-3 flex-shrink-0">
                    {expanded ? "▼" : "▶"}
                  </span>
                  <span className="text-xs font-bold text-blue-700 whitespace-nowrap">
                    {s.site_id}
                  </span>
                  <span className="text-[10px] text-emerald-600 whitespace-nowrap">
                    {s.milestone_status_summary.on_track} on track
                  </span>
                  <span className="text-[10px] text-blue-500 whitespace-nowrap">
                    {s.milestone_status_summary.in_progress} in progress
                  </span>
                  {s.milestone_status_summary.delayed > 0 && (
                    <span className="text-[10px] text-red-500 whitespace-nowrap">
                      {s.milestone_status_summary.delayed} delayed
                    </span>
                  )}
                  <span className="text-[10px] text-gray-400 ml-auto whitespace-nowrap">
                    Forecast: {s.forecasted_cx_start_date || "TBD"}
                  </span>
                  <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded-full border whitespace-nowrap ${badge.cls}`}>
                    {badge.label}
                  </span>
                </div>
              );
            }

            const m = row.milestone;
            return (
              <div
                key={`l-m-${row.site.site_id}-${m.key}`}
                className="flex items-center pl-12 pr-3 border-b border-gray-50"
                style={{ height: ROW_H, background: idx % 2 === 0 ? "#fff" : "#fafbfc" }}
              >
                <span className="text-[11px] font-medium text-gray-600">{getMilestoneName(m)}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Draggable divider */}
      <div
        onMouseDown={onDragStart}
        className="flex-shrink-0 w-1.5 cursor-col-resize bg-gray-200 hover:bg-blue-400 active:bg-blue-500 transition-colors relative group"
      >
        <div className="absolute inset-y-0 -left-1 -right-1" />
        <div className="absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-0.5 h-8 bg-gray-400 group-hover:bg-white rounded-full" />
      </div>

      {/* RIGHT: Chart */}
      <div className="flex-1 overflow-auto" ref={scrollRef}>
        <div style={{ width: chartW, minWidth: "100%" }}>
          {/* Column headers */}
          <div className="sticky top-0 z-10 flex border-b border-gray-200 bg-gray-50" style={{ height: HEADER_H }}>
            {columns.map((c, i) => (
              <div
                key={i}
                className="flex-shrink-0 flex flex-col items-center justify-center border-r border-gray-100"
                style={{ width: colW }}
              >
                <span className="text-[10px] font-semibold text-gray-500">{c.label}</span>
                {c.sub && <span className="text-[9px] text-gray-400">{c.sub}</span>}
              </div>
            ))}
          </div>

          {/* Rows */}
          <div className="relative">
            {/* Today line */}
            {todayX > 0 && todayX < chartW && (
              <div className="absolute top-0 bottom-0 z-20 pointer-events-none" style={{ left: todayX, width: 2, background: "#3b82f6" }}>
                <div className="absolute -top-5 -translate-x-1/2 bg-blue-600 text-white text-[9px] px-1.5 py-0.5 rounded font-semibold">
                  Today
                </div>
              </div>
            )}

            {rows.map((row, idx) => {
              // Vendor row
              if (row.type === "vendor") {
                return (
                  <div
                    key={`c-v-${row.vendorName}`}
                    className="relative border-b border-gray-200"
                    style={{ height: ROW_H, background: "#e0e7ff" }}
                  >
                    {columns.map((_, ci) => (
                      <div key={ci} className="absolute top-0 bottom-0 border-r border-indigo-100/30" style={{ left: ci * colW, width: colW }} />
                    ))}
                  </div>
                );
              }

              // Site row
              if (row.type === "site") {
                return (
                  <div
                    key={`c-s-${row.site.site_id}`}
                    className="relative border-b border-gray-100"
                    style={{ height: ROW_H, background: "#f0f4ff" }}
                  >
                    {columns.map((_, ci) => (
                      <div key={ci} className="absolute top-0 bottom-0 border-r border-gray-50" style={{ left: ci * colW, width: colW }} />
                    ))}
                  </div>
                );
              }

              // Milestone row
              const m = row.milestone;
              const barColor = getBarColor(m);
              const startColIdx = dateToColIndex(m.planned_start);
              const endColIdx = dateToColIndex(m.planned_finish);
              const bgColor = idx % 2 === 0 ? "#fff" : "#fafbfc";

              const barLeft = startColIdx != null ? startColIdx * colW + 2 : 0;
              const barRight = endColIdx != null ? (endColIdx + 1) * colW - 2 : barLeft + colW - 4;
              const barWidth = startColIdx != null ? Math.max(barRight - barLeft, colW - 4) : colW - 4;

              const isDelayed = m.status === "Delayed" && m.delay_days > 0;
              const delayEndColIdx = isDelayed ? dateToColIndex(new Date().toISOString().slice(0, 10)) : null;
              const delayWidth = isDelayed && delayEndColIdx != null && endColIdx != null && delayEndColIdx > endColIdx
                ? ((delayEndColIdx - endColIdx) * colW) : 0;

              const barTop = 6;
              const barH = 24;

              return (
                <div
                  key={`c-m-${row.site.site_id}-${m.key}`}
                  className="relative border-b border-gray-100 group"
                  style={{ height: ROW_H, background: bgColor }}
                >
                  {/* Grid */}
                  {columns.map((_, ci) => (
                    <div key={ci} className="absolute top-0 bottom-0 border-r border-gray-50" style={{ left: ci * colW, width: colW }} />
                  ))}

                  {/* Solid filled bar */}
                  {startColIdx != null && (
                    <div
                      className="absolute"
                      style={{
                        left: barLeft,
                        width: barWidth,
                        top: barTop,
                        height: barH,
                        background: barColor,
                        borderRadius: 3,
                      }}
                    />
                  )}

                  {/* Delay extension bar (striped red) */}
                  {isDelayed && endColIdx != null && delayWidth > 0 && (
                    <div
                      className="absolute"
                      style={{
                        left: barRight,
                        width: delayWidth,
                        top: barTop,
                        height: barH,
                        borderRadius: "0 3px 3px 0",
                        background: "repeating-linear-gradient(135deg, #fca5a5, #fca5a5 3px, #f87171 3px, #f87171 6px)",
                      }}
                    />
                  )}

                  {/* Hover tooltip */}
                  <div
                    className="absolute hidden group-hover:flex z-30 items-center gap-2 px-2.5 py-1.5 rounded-lg text-[10px] whitespace-nowrap pointer-events-none"
                    style={{
                      left: barLeft,
                      top: -30,
                      background: "#1e293b",
                      color: "#f1f5f9",
                      boxShadow: "0 4px 16px rgba(0,0,0,0.2)",
                    }}
                  >
                    <span className="font-semibold">{getMilestoneName(m)}</span>
                    <span className="text-gray-400">|</span>
                    <span>{m.planned_start} → {m.planned_finish}</span>
                    {m.delay_days > 0 && (
                      <span className="text-red-300 font-semibold">+{m.delay_days}d</span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </div>
  );
}
