import { ArchiveViewSwitcher } from "@/components/archive/ArchiveViewSwitcher";
import { ArchiveQuickPostInline } from "@/components/archive/ArchiveQuickPostInline";
import { PageMenuHeading } from "@/components/layout/PageMenuHeading";

export default function ArchivePage() {
  return (
    <section className="space-y-4">
      <div className="grid gap-4 lg:grid-cols-[minmax(250px,1.8fr)_minmax(0,10.2fr)] lg:items-start">
        <PageMenuHeading title="아카이브" href="/archive" />
        <div className="w-full min-w-0">
          <ArchiveQuickPostInline />
        </div>
      </div>
      <ArchiveViewSwitcher />
    </section>
  );
}
