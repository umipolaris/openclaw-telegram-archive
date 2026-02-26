import { ReviewQueueManager } from "@/components/review/ReviewQueueManager";
import { PageMenuHeading } from "@/components/layout/PageMenuHeading";

export default function ReviewQueuePage() {
  return (
    <section className="space-y-4">
      <PageMenuHeading title="검토 큐" href="/review-queue" />
      <ReviewQueueManager />
    </section>
  );
}
