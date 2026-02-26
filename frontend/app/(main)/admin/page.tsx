import { AdminWorkspace } from "@/components/admin/AdminWorkspace";
import { RoleGate } from "@/components/auth/RoleGate";
import { PageMenuHeading } from "@/components/layout/PageMenuHeading";

export default function AdminPage() {
  return (
    <section className="space-y-4">
      <PageMenuHeading title="관리자" href="/admin" />
      <RoleGate allowedRoles={["ADMIN"]}>
        <AdminWorkspace />
      </RoleGate>
    </section>
  );
}
