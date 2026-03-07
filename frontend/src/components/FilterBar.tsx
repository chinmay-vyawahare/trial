"use client";

interface Props {
  markets: string[];
  selectedMarket: string;
  selectedStatus: string;
  onMarketChange: (market: string) => void;
  onStatusChange: (status: string) => void;
}

const statuses = [
  { value: "", label: "All Statuses" },
  { value: "COMPLETED", label: "Completed" },
  { value: "IN_PROGRESS", label: "In Progress" },
  { value: "PENDING", label: "Pending" },
  { value: "DELAYED", label: "Delayed / Critical" },
];

export default function FilterBar({
  markets,
  selectedMarket,
  selectedStatus,
  onMarketChange,
  onStatusChange,
}: Props) {
  return (
    <div className="flex flex-wrap gap-3 mb-4">
      <select
        value={selectedMarket}
        onChange={(e) => onMarketChange(e.target.value)}
        className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        <option value="">All Markets</option>
        {markets.map((m) => (
          <option key={m} value={m}>
            {m}
          </option>
        ))}
      </select>
      <select
        value={selectedStatus}
        onChange={(e) => onStatusChange(e.target.value)}
        className="px-3 py-1.5 border border-gray-300 rounded-lg text-sm bg-white focus:outline-none focus:ring-2 focus:ring-blue-500"
      >
        {statuses.map((s) => (
          <option key={s.value} value={s.value}>
            {s.label}
          </option>
        ))}
      </select>
    </div>
  );
}
