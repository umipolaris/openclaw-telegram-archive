"use client";

import { useState } from "react";
import { ListTree, Layers3 } from "lucide-react";

import { ArchiveSetWorkspace } from "@/components/archive/ArchiveSetWorkspace";
import { ArchiveWorkspace } from "@/components/archive/ArchiveWorkspace";

type ArchiveViewMode = "tree" | "set";

export function ArchiveViewSwitcher() {
  const [viewMode, setViewMode] = useState<ArchiveViewMode>("tree");

  return (
    <div className="space-y-3">
      <div className="inline-flex rounded-lg border border-stone-300 bg-white p-1 text-sm">
        <button
          className={`inline-flex items-center gap-1 rounded px-3 py-1 ${viewMode === "tree" ? "bg-accent text-white" : "text-stone-700 hover:bg-stone-100"}`}
          onClick={() => setViewMode("tree")}
        >
          <ListTree className="h-4 w-4" />
          기본 목록 보기
        </button>
        <button
          className={`inline-flex items-center gap-1 rounded px-3 py-1 ${viewMode === "set" ? "bg-accent text-white" : "text-stone-700 hover:bg-stone-100"}`}
          onClick={() => setViewMode("set")}
        >
          <Layers3 className="h-4 w-4" />
          세트/개정 보기
        </button>
      </div>

      {viewMode === "tree" ? <ArchiveWorkspace /> : <ArchiveSetWorkspace />}
    </div>
  );
}
