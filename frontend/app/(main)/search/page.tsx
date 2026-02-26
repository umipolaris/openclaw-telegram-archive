import { SearchWorkspace } from "@/components/search/SearchWorkspace";
import { PageMenuHeading } from "@/components/layout/PageMenuHeading";

export default function SearchPage() {
  return (
    <section className="space-y-4">
      <PageMenuHeading title="검색" href="/search" />
      <SearchWorkspace />
    </section>
  );
}
