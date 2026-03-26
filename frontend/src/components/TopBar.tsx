"use client";

import { useState } from "react";
import Link from "next/link";

interface Props {
  userId: string;
  onUserIdApply: (userId: string) => void;
}

export default function TopBar({ userId, onUserIdApply }: Props) {
  const [input, setInput] = useState(userId);

  function handleApply() {
    const trimmed = input.trim();
    onUserIdApply(trimmed);
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleApply();
  }

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
        <label className="text-xs font-medium text-gray-500">User ID:</label>
        <input
          type="text"
          placeholder="Enter User ID"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          className="px-2.5 py-1.5 text-xs rounded-lg border border-gray-200 bg-white text-gray-800 focus:outline-none focus:ring-2 focus:ring-blue-400 w-40"
        />
        <button
          onClick={handleApply}
          className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors shadow-sm"
        >
          Apply
        </button>
        {userId && (
          <span className="px-2.5 py-1 text-[11px] font-medium rounded-full bg-green-50 text-green-700 border border-green-200">
            {userId}
          </span>
        )}
        <span className="px-3 py-1 text-xs font-semibold rounded-full bg-blue-50 text-blue-700 border border-blue-200">
          MODE: PLANNER
        </span>
        <Link
          href="/test-api"
          className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-gradient-to-r from-violet-500 to-fuchsia-500 text-white hover:from-violet-600 hover:to-fuchsia-600 transition-all shadow-sm"
        >
          Test APIs
        </Link>
      </div>
    </header>
  );
}
