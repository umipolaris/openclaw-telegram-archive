import Link from "next/link";
import { Pencil } from "lucide-react";
import { ArchiveViewSwitcher } from "@/components/archive/ArchiveViewSwitcher";
import { PageMenuHeading } from "@/components/layout/PageMenuHeading";

export default function ArchivePage() {
  return (
    <section className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <PageMenuHeading title="아카이브" href="/archive" />
        <Link
          href="/manual-post"
          className="inline-flex items-center gap-1 rounded-md border border-stone-300 bg-white px-2.5 py-1.5 text-xs font-medium text-stone-700 shadow-sm hover:bg-stone-100"
        >
          <Pencil className="h-3.5 w-3.5" />
          수동게시
        </Link>
      </div>
      <ArchiveViewSwitcher />
    </section>
  );
}
