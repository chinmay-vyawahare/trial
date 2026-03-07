"use client";

export default function TopBar() {
  return (
    <header className="flex items-center justify-between px-5 py-2.5 bg-white border-b border-gray-200 shadow-sm">
      <div className="flex items-center gap-3">
        <div className="w-9 h-9 rounded-lg bg-blue-600 flex items-center justify-center text-white text-sm font-bold">
          N
        </div>
        <div>
          <h1 className="text-base font-bold text-gray-900">Nokia Site Tracker</h1>
          <p className="text-[11px] text-gray-500">Telecom Deployment Intelligence</p>
        </div>
      </div>
      <div className="flex items-center gap-3">
        <span className="px-3 py-1 text-xs font-semibold rounded-full bg-blue-50 text-blue-700 border border-blue-200">
          MODE: PLANNER
        </span>
      </div>
    </header>
  );
}
