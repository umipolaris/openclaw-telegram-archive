"use client";

import { useState } from "react";
import { Pencil } from "lucide-react";
import { ModalShell } from "@/components/common/ModalShell";
import { QuickPostComposer } from "@/components/manual/QuickPostComposer";

export function ArchiveQuickPostButton() {
  const [open, setOpen] = useState(false);
  const handleSuccess = () => {
    setOpen(false);
    window.dispatchEvent(new Event("archive:refresh"));
  };

  return (
    <>
      <button
        type="button"
        className="inline-flex items-center gap-1 rounded-md border border-emerald-300 bg-emerald-50 px-2.5 py-1.5 text-xs font-medium text-emerald-800 shadow-sm hover:bg-emerald-100"
        onClick={() => setOpen(true)}
      >
        <Pencil className="h-3.5 w-3.5" />
        간편게시
      </button>
      <ModalShell open={open} title="간편게시" onClose={() => setOpen(false)} maxWidthClassName="max-w-2xl">
        <QuickPostComposer compact onSuccess={handleSuccess} />
      </ModalShell>
    </>
  );
}
