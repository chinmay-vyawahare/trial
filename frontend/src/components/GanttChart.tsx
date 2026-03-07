"use client";

import { Milestone, SiteGantt } from "@/lib/types";
import { useState, useMemo, useRef } from "react";
import {
  format,
  parseISO,
  differenceInDays,
  addDays,
  eachDayOfInterval,
  eachWeekOfInterval,
  eachMonthOfInterval,
} from "date-fns";

type TimelineView = "daily" | "weekly" | "monthly" | "quarterly" | "yearly";

interface Props {
  site: SiteGantt;
}

function getStatusColor(status: string): string {
  if (status === "On Track") return "#22c55e";
  if (status === "In Progress") return "#eab308";
  if (status === "Delayed") return "#ef4444";
  return "#94a3b8";
}

function getDateRange(milestones: Milestone[]) {
  let minDate: Date | null = null;
  let maxDate: Date | null = null;
  for (const m of milestones) {
    for (const d of [m.planned_start, m.planned_finish, m.actual_finish]) {
      if (d && d.match(/^\d{4}-\d{2}-\d{2}/)) {
        const dt = parseISO(d);
        if (!minDate || dt < minDate) minDate = dt;
        if (!maxDate || dt > maxDate) maxDate = dt;
      }
    }
  }
  if (!minDate) minDate = new Date();
  if (!maxDate) maxDate = addDays(new Date(), 180);
  return {
    start: addDays(minDate, -7),
    end: addDays(maxDate, 14),
  };
}

function getTimelineLabels(start: Date, end: Date, view: TimelineView) {
  switch (view) {
    case "daily":
      return eachDayOfInterval({ start, end }).map((d) => ({
        date: d,
        label: format(d, "MMM dd"),
        subLabel: format(d, "EEE"),
      }));
    case "weekly":
      return eachWeekOfInterval({ start, end }).map((d) => ({
        date: d,
        label: format(d, "MMM dd"),
        subLabel: `W${format(d, "ww")}`,
      }));
    case "monthly":
      return eachMonthOfInterval({ start, end }).map((d) => ({
        date: d,
        label: format(d, "MMM yyyy"),
        subLabel: "",
      }));
    case "quarterly": {
      const months = eachMonthOfInterval({ start, end });
      return months
        .filter((_, i) => i % 3 === 0)
        .map((d) => ({
          date: d,
          label: `Q${Math.ceil((d.getMonth() + 1) / 3)} ${format(d, "yyyy")}`,
          subLabel: "",
        }));
    }
    case "yearly": {
      const months = eachMonthOfInterval({ start, end });
      return months
        .filter((d) => d.getMonth() === 0)
        .concat(months.length > 0 ? [months[0]] : [])
        .filter((v, i, a) => a.findIndex((x) => x.getFullYear() === v.getFullYear()) === i)
        .map((d) => ({
          date: d,
          label: format(d, "yyyy"),
          subLabel: "",
        }));
    }
  }
}

function getColWidth(view: TimelineView) {
  switch (view) {
    case "daily": return 32;
    case "weekly": return 60;
    case "monthly": return 100;
    case "quarterly": return 140;
    case "yearly": return 200;
  }
}

const ROW_HEIGHT = 40;
const LABEL_WIDTH = 280;

export default function GanttChart({ site }: Props) {
  const [view, setView] = useState<TimelineView>("weekly");
  const [hoveredMs, setHoveredMs] = useState<string | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);

  const { start: rangeStart, end: rangeEnd } = useMemo(
    () => getDateRange(site.milestones),
    [site.milestones]
  );
  const totalDays = differenceInDays(rangeEnd, rangeStart);
  const colWidth = getColWidth(view);
  const labels = useMemo(
    () => getTimelineLabels(rangeStart, rangeEnd, view),
    [rangeStart, rangeEnd, view]
  );
  const chartWidth = labels.length * colWidth;

  function dateToX(d: string | null) {
    if (!d) return null;
    const dt = parseISO(d);
    const days = differenceInDays(dt, rangeStart);
    return (days / totalDays) * chartWidth;
  }

  const todayX = (() => {
    const days = differenceInDays(new Date(), rangeStart);
    return (days / totalDays) * chartWidth;
  })();

  const sortedMilestones = [...site.milestones].sort(
    (a, b) => a.sort_order - b.sort_order
  );

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 overflow-hidden">
      {/* Header */}
      <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
        <div>
          <h3 className="font-bold text-gray-800">
            {site.site_id} — {site.project_name}
          </h3>
          <p className="text-xs text-gray-500">
            {site.market} | Cx Start: {site.forecasted_cx_start_date || "TBD"}
          </p>
        </div>
        <div className="flex gap-1">
          {(["daily", "weekly", "monthly", "quarterly", "yearly"] as TimelineView[]).map(
            (v) => (
              <button
                key={v}
                onClick={() => setView(v)}
                className={`px-3 py-1 text-xs font-medium rounded-md transition-colors ${
                  view === v
                    ? "bg-blue-600 text-white"
                    : "bg-gray-100 text-gray-600 hover:bg-gray-200"
                }`}
              >
                {v.charAt(0).toUpperCase() + v.slice(1)}
              </button>
            )
          )}
        </div>
      </div>

      {/* Chart */}
      <div className="flex">
        {/* Left labels */}
        <div
          className="flex-shrink-0 border-r border-gray-200 bg-gray-50"
          style={{ width: LABEL_WIDTH }}
        >
          <div className="h-12 border-b border-gray-200 px-3 flex items-center">
            <span className="text-xs font-semibold text-gray-500 uppercase">
              Milestone
            </span>
          </div>
          {sortedMilestones.map((m) => {
            const color = getStatusColor(m.status);
            return (
              <div
                key={m.key}
                className="flex items-center px-3 border-b border-gray-50 hover:bg-gray-100 transition-colors"
                style={{ height: ROW_HEIGHT }}
                onMouseEnter={() => setHoveredMs(m.key)}
                onMouseLeave={() => setHoveredMs(null)}
              >
                <div
                  className="w-2.5 h-2.5 rounded-full mr-2 flex-shrink-0"
                  style={{ backgroundColor: color }}
                />
                <div className="min-w-0">
                  <div className="text-xs font-medium text-gray-700 truncate">
                    {m.name}
                  </div>
                  <div className="text-[10px] text-gray-400">{m.status}</div>
                </div>
              </div>
            );
          })}
        </div>

        {/* Scrollable chart area */}
        <div className="flex-1 overflow-x-auto" ref={scrollRef}>
          <div style={{ width: chartWidth, minWidth: "100%" }}>
            {/* Timeline header */}
            <div className="h-12 border-b border-gray-200 flex relative">
              {labels.map((l, i) => (
                <div
                  key={i}
                  className="flex-shrink-0 border-r border-gray-100 flex flex-col items-center justify-center"
                  style={{ width: colWidth }}
                >
                  <span className="text-[10px] font-medium text-gray-600">
                    {l.label}
                  </span>
                  {l.subLabel && (
                    <span className="text-[9px] text-gray-400">
                      {l.subLabel}
                    </span>
                  )}
                </div>
              ))}
            </div>

            {/* Rows */}
            <div className="relative">
              {/* Today line */}
              {todayX > 0 && todayX < chartWidth && (
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-red-400 z-20 pointer-events-none"
                  style={{ left: todayX }}
                >
                  <div className="absolute -top-5 -translate-x-1/2 bg-red-500 text-white text-[9px] px-1.5 py-0.5 rounded font-medium">
                    Today
                  </div>
                </div>
              )}

              {/* Grid lines */}
              {labels.map((_, i) => (
                <div
                  key={i}
                  className="absolute top-0 bottom-0 border-r border-gray-50"
                  style={{ left: i * colWidth }}
                />
              ))}

              {sortedMilestones.map((m) => {
                const statusColor = getStatusColor(m.status);
                const plannedStartX = dateToX(m.planned_start);
                const plannedFinishX = dateToX(m.planned_finish);
                const actualFinishX = dateToX(m.actual_finish);

                const barStart = plannedStartX ?? 0;
                const barEnd = plannedFinishX ?? barStart;
                const barWidth = Math.max(barEnd - barStart, 6);

                const isHovered = hoveredMs === m.key;
                const isCompleted = m.actual_finish !== null;
                const isDelayed = m.status === "Delayed" && m.delay_days > 0;

                return (
                  <div
                    key={m.key}
                    className="relative border-b border-gray-50"
                    style={{ height: ROW_HEIGHT }}
                    onMouseEnter={() => setHoveredMs(m.key)}
                    onMouseLeave={() => setHoveredMs(null)}
                  >
                    {/* Planned bar (background) */}
                    {plannedStartX !== null && (
                      <div
                        className="absolute top-2 h-4 rounded opacity-30"
                        style={{
                          left: barStart,
                          width: barWidth,
                          backgroundColor: statusColor,
                        }}
                      />
                    )}

                    {/* Actual / Status bar */}
                    <div
                      className="absolute top-2 h-4 rounded shadow-sm transition-all"
                      style={{
                        left: barStart,
                        width: isCompleted
                          ? barWidth
                          : actualFinishX
                          ? Math.max(actualFinishX - barStart, 6)
                          : Math.max(
                              ((todayX - barStart) / barWidth) * barWidth,
                              0
                            ),
                        backgroundColor: statusColor,
                        opacity: 0.9,
                        transform: isHovered ? "scaleY(1.3)" : "scaleY(1)",
                        transformOrigin: "center",
                      }}
                    />

                    {/* Delay extension (red bar) */}
                    {isDelayed && plannedFinishX !== null && todayX > plannedFinishX && (
                      <div
                        className="absolute top-2.5 h-3 rounded-r"
                        style={{
                          left: plannedFinishX,
                          width: todayX - plannedFinishX,
                          backgroundColor: "#ef4444",
                          opacity: 0.6,
                        }}
                      />
                    )}

                    {/* Actual finish diamond */}
                    {actualFinishX !== null && (
                      <div
                        className="absolute top-1.5 w-3 h-3 rotate-45 border-2 border-white shadow"
                        style={{
                          left: actualFinishX - 6,
                          backgroundColor: isCompleted ? "#22c55e" : statusColor,
                        }}
                      />
                    )}

                    {/* Duration label */}
                    {isHovered && plannedStartX !== null && (
                      <div
                        className="absolute top-6 text-[9px] font-medium text-gray-600 whitespace-nowrap z-30 bg-white/90 px-1 rounded shadow-sm"
                        style={{ left: barStart }}
                      >
                        {m.planned_start} → {m.planned_finish}
                        {m.delay_days > 0 && (
                          <span className="text-red-600 ml-1">
                            (+{m.delay_days}d delay)
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* Legend */}
      <div className="px-4 py-2 border-t border-gray-100 flex flex-wrap gap-4 text-xs text-gray-500">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded bg-emerald-500" />
          <span>On Track</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded bg-yellow-500" />
          <span>In Progress</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded bg-red-500" />
          <span>Delayed</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-0.5 h-3 bg-red-400" />
          <span>Today</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rotate-45 bg-emerald-500 border border-white" />
          <span>Actual Finish</span>
        </div>
      </div>
    </div>
  );
}
