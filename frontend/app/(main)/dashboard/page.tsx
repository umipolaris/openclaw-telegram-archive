import { DashboardSummary } from "@/components/dashboard/DashboardSummary";
import { PageMenuHeading } from "@/components/layout/PageMenuHeading";

export default function DashboardPage() {
  return (
    <section className="space-y-4">
      <PageMenuHeading title="대시보드" href="/dashboard" />
      <DashboardSummary />
    </section>
  );
}
