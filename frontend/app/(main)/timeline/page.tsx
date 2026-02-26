import { TimelineViewer } from "@/components/timeline/TimelineViewer";
import { PageMenuHeading } from "@/components/layout/PageMenuHeading";

export default function TimelinePage() {
  return (
    <section className="space-y-4">
      <PageMenuHeading title="타임라인" href="/timeline" />
      <TimelineViewer />
    </section>
  );
}
