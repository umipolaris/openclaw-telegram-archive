import { apiGet } from "@/lib/api-client";

export type UserRole = "ADMIN" | "EDITOR" | "REVIEWER" | "VIEWER";

export interface SessionUser {
  id: string;
  username: string;
  role: UserRole;
}

export async function getCurrentUser(): Promise<SessionUser | null> {
  try {
    const user = await apiGet<SessionUser>("/auth/me");
    return user;
  } catch {
    return null;
  }
}
