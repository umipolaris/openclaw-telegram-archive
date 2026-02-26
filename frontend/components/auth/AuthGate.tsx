"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { apiGet } from "@/lib/api-client";

type AuthUser = {
  id: string;
  username: string;
  role: "ADMIN" | "EDITOR" | "REVIEWER" | "VIEWER";
};

export function AuthGate({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    let resolved = false;
    const next = encodeURIComponent(pathname || "/archive");
    const timeoutId = window.setTimeout(() => {
      if (cancelled || resolved) return;
      window.location.assign(`/login?next=${next}`);
    }, 8000);

    async function checkAuth() {
      try {
        await apiGet<AuthUser>("/auth/me");
        if (!cancelled) {
          resolved = true;
          window.clearTimeout(timeoutId);
          setReady(true);
        }
      } catch {
        if (!cancelled) {
          resolved = true;
          window.clearTimeout(timeoutId);
          window.location.assign(`/login?next=${next}`);
        }
      }
    }

    void checkAuth();
    return () => {
      cancelled = true;
      window.clearTimeout(timeoutId);
    };
  }, [pathname]);

  if (!ready) {
    return <div className="p-6 text-sm text-stone-600">세션 확인 중...</div>;
  }

  return <>{children}</>;
}
