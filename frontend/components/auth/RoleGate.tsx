"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { getCurrentUser, type UserRole } from "@/lib/auth";
import { userRoleLabel } from "@/lib/labels";

export function RoleGate({
  allowedRoles,
  children,
}: {
  allowedRoles: UserRole[];
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const [loading, setLoading] = useState(true);
  const [forbidden, setForbidden] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function checkRole() {
      setLoading(true);
      const user = await getCurrentUser();
      if (cancelled) return;

      if (!user) {
        const next = encodeURIComponent(pathname || "/archive");
        window.location.assign(`/login?next=${next}`);
        return;
      }

      setForbidden(!allowedRoles.includes(user.role));
      setLoading(false);
    }

    void checkRole();
    return () => {
      cancelled = true;
    };
  }, [allowedRoles, pathname]);

  if (loading) {
    return <p className="text-sm text-stone-600">권한 확인 중...</p>;
  }

  if (forbidden) {
    const roleText = allowedRoles.map((role) => userRoleLabel(role)).join(", ");
    return (
      <article className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-800">
        <p className="font-semibold">접근 권한이 없습니다.</p>
        <p className="mt-1">허용 역할: {roleText}</p>
        <button
          className="mt-3 rounded border border-red-300 px-3 py-1 text-xs hover:bg-red-100"
          onClick={() => window.location.assign("/archive")}
        >
          아카이브로 이동
        </button>
      </article>
    );
  }

  return <>{children}</>;
}
