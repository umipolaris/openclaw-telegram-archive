import { RoleGate } from "@/components/auth/RoleGate";
import { RulesWorkspace } from "@/components/rules/RulesWorkspace";
import { PageMenuHeading } from "@/components/layout/PageMenuHeading";

export default function RulesPage() {
  return (
    <section className="space-y-4">
      <PageMenuHeading title="규칙" href="/rules" />
      <RoleGate allowedRoles={["REVIEWER", "ADMIN"]}>
        <RulesWorkspace />
      </RoleGate>
    </section>
  );
}
