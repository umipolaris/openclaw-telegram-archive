import { PageMenuHeading } from "@/components/layout/PageMenuHeading";
import { MindMapWorkspace } from "@/components/mindmap/MindMapWorkspace";

export default function MindMapPage() {
  return (
    <section className="space-y-4">
      <PageMenuHeading title="마인드맵" href="/mind-map" />
      <MindMapWorkspace />
    </section>
  );
}
