import { ArchiveViewSwitcher } from "@/components/archive/ArchiveViewSwitcher";
import { PageMenuHeading } from "@/components/layout/PageMenuHeading";

export default function ArchivePage() {
  return (
    <section className="space-y-4">
      <PageMenuHeading title="아카이브" href="/archive" />
      <ArchiveViewSwitcher />
    </section>
  );
}
