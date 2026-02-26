"use client";

import { useState } from "react";
import { History, Users } from "lucide-react";
import { AdminLogViewer } from "@/components/admin/AdminLogViewer";
import { AdminUserManager } from "@/components/admin/AdminUserManager";

type AdminTab = "users" | "logs";

export function AdminWorkspace() {
  const [tab, setTab] = useState<AdminTab>("users");

  return (
    <section className="space-y-4">
      <div className="flex gap-2">
        <button
          className={`inline-flex items-center gap-1 rounded border px-3 py-1 text-sm ${tab === "users" ? "border-accent bg-accent text-white" : "border-stone-300 hover:bg-stone-50"}`}
          onClick={() => setTab("users")}
        >
          <Users className="h-4 w-4" />
          사용자 관리
        </button>
        <button
          className={`inline-flex items-center gap-1 rounded border px-3 py-1 text-sm ${tab === "logs" ? "border-accent bg-accent text-white" : "border-stone-300 hover:bg-stone-50"}`}
          onClick={() => setTab("logs")}
        >
          <History className="h-4 w-4" />
          운영/감사 로그
        </button>
      </div>

      {tab === "users" ? <AdminUserManager /> : null}
      {tab === "logs" ? <AdminLogViewer /> : null}
    </section>
  );
}
