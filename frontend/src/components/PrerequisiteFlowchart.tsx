"use client";

import { useEffect, useRef, useState } from "react";
import { getPrerequisiteFlowchart } from "@/lib/api";

export default function PrerequisiteFlowchart() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    async function render() {
      try {
        const mermaidCode = await getPrerequisiteFlowchart();
        if (cancelled || !containerRef.current) return;

        // Dynamic import to avoid SSR issues
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          theme: "default",
          flowchart: { useMaxWidth: true, htmlLabels: true, curve: "basis" },
          securityLevel: "loose",
        });

        const { svg } = await mermaid.render("prereq-flowchart", mermaidCode);
        if (cancelled || !containerRef.current) return;
        containerRef.current.innerHTML = svg;
        setLoading(false);
      } catch (e) {
        if (!cancelled) {
          setError(e instanceof Error ? e.message : "Failed to load flowchart");
          setLoading(false);
        }
      }
    }

    render();
    return () => { cancelled = true; };
  }, []);

  if (error) {
    return (
      <div className="flex items-center justify-center h-full text-red-500 text-sm">
        {error}
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto bg-white p-4">
      {loading && (
        <div className="flex items-center justify-center h-full">
          <div className="animate-spin w-6 h-6 border-2 border-blue-500 border-t-transparent rounded-full" />
        </div>
      )}
      <div ref={containerRef} className="flex justify-center" />
    </div>
  );
}
