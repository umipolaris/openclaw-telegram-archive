"use client";

import { QuickPostComposer } from "@/components/manual/QuickPostComposer";

export function ArchiveQuickPostInline() {
  const refreshArchive = () => {
    window.dispatchEvent(new Event("archive:refresh"));
  };

  return (
    <section className="w-full min-w-0">
      <QuickPostComposer compact inline onQueued={refreshArchive} onSuccess={refreshArchive} />
    </section>
  );
}
