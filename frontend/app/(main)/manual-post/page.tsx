import { RoleGate } from "@/components/auth/RoleGate";
import { ManualPostComposer } from "@/components/manual/ManualPostComposer";
import { PageMenuHeading } from "@/components/layout/PageMenuHeading";

export default function ManualPostPage() {
  return (
    <section className="space-y-4">
      <PageMenuHeading title="수동 게시" href="/manual-post" />
      <RoleGate allowedRoles={["EDITOR", "ADMIN"]}>
        <ManualPostComposer />
      </RoleGate>
    </section>
  );
}
