"use client";

interface MarketData {
  market: string;
  total: number;
  on_track: number;
  in_progress: number;
  critical: number;
}

interface Props {
  markets: MarketData[];
}

export default function MarketChart({ markets }: Props) {
  const maxTotal = Math.max(...markets.map((m) => m.total), 1);

  return (
    <div className="bg-white rounded-xl shadow border border-gray-200 p-4">
      <h3 className="font-bold text-gray-800 mb-4">Market Overview</h3>
      <div className="space-y-3">
        {markets.map((m) => (
          <div key={m.market}>
            <div className="flex items-center justify-between mb-1">
              <span className="text-sm font-medium text-gray-700">{m.market}</span>
              <span className="text-xs text-gray-500">{m.total} sites</span>
            </div>
            <div className="flex h-5 rounded-full overflow-hidden bg-gray-100">
              {m.on_track > 0 && (
                <div
                  className="bg-emerald-500 transition-all"
                  style={{ width: `${(m.on_track / maxTotal) * 100}%` }}
                  title={`${m.on_track} on track`}
                />
              )}
              {m.in_progress > 0 && (
                <div
                  className="bg-amber-500 transition-all"
                  style={{ width: `${(m.in_progress / maxTotal) * 100}%` }}
                  title={`${m.in_progress} in progress`}
                />
              )}
              {m.critical > 0 && (
                <div
                  className="bg-red-500 transition-all"
                  style={{ width: `${(m.critical / maxTotal) * 100}%` }}
                  title={`${m.critical} critical`}
                />
              )}
            </div>
          </div>
        ))}
      </div>
      <div className="flex gap-4 mt-4 text-xs text-gray-500">
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-emerald-500" /> On Track
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-amber-500" /> In Progress
        </div>
        <div className="flex items-center gap-1">
          <div className="w-3 h-3 rounded bg-red-500" /> Critical
        </div>
      </div>
    </div>
  );
}
