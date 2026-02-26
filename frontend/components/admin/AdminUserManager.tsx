"use client";

import { useCallback, useEffect, useState } from "react";
import { RefreshCcw, Search, User, Users } from "lucide-react";
import { apiFetch, apiGet, apiPost } from "@/lib/api-client";
import { userRoleLabel } from "@/lib/labels";

type UserRole = "ADMIN" | "EDITOR" | "REVIEWER" | "VIEWER";

type UserSummary = {
  id: string;
  username: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
};

type UsersListResponse = {
  items: UserSummary[];
  page: number;
  size: number;
  total: number;
};

type AuthMe = {
  id: string;
  username: string;
  role: UserRole;
};

type UpdateUserRequest = {
  role?: UserRole;
  is_active?: boolean;
  password?: string;
};

type DeleteUserResponse = {
  id: string;
  username: string;
  deleted: boolean;
  nullified_refs: Record<string, number>;
};

const ROLE_OPTIONS: UserRole[] = ["ADMIN", "EDITOR", "REVIEWER", "VIEWER"];
const PAGE_SIZE = 20;

function formatDateTime(value: string | null): string {
  if (!value) return "-";
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? "-" : dt.toLocaleString("ko-KR");
}

export function AdminUserManager() {
  const [currentUserId, setCurrentUserId] = useState("");
  const [users, setUsers] = useState<UserSummary[]>([]);
  const [roleDrafts, setRoleDrafts] = useState<Record<string, UserRole>>({});
  const [passwordDrafts, setPasswordDrafts] = useState<Record<string, string>>({});
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [roleFilter, setRoleFilter] = useState<UserRole | "">("");
  const [activeFilter, setActiveFilter] = useState<"" | "true" | "false">("");
  const [loading, setLoading] = useState(true);
  const [busyUserId, setBusyUserId] = useState<string | null>(null);

  const [newUsername, setNewUsername] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [newRole, setNewRole] = useState<UserRole>("VIEWER");
  const [creating, setCreating] = useState(false);

  const [error, setError] = useState("");
  const [message, setMessage] = useState("");

  const loadUsers = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("size", String(PAGE_SIZE));
      if (query.trim()) params.set("q", query.trim());
      if (roleFilter) params.set("role", roleFilter);
      if (activeFilter) params.set("is_active", activeFilter);

      const res = await apiGet<UsersListResponse>(`/admin/users?${params.toString()}`);
      setUsers(res.items);
      setTotal(res.total);
      setRoleDrafts(Object.fromEntries(res.items.map((u) => [u.id, u.role])));
    } catch (err) {
      setError(err instanceof Error ? err.message : "사용자 목록 로드 실패");
    } finally {
      setLoading(false);
    }
  }, [activeFilter, page, query, roleFilter]);

  useEffect(() => {
    void loadUsers();
  }, [loadUsers]);

  useEffect(() => {
    let cancelled = false;
    async function loadMe() {
      try {
        const me = await apiGet<AuthMe>("/auth/me");
        if (!cancelled) setCurrentUserId(me.id);
      } catch {
        if (!cancelled) setCurrentUserId("");
      }
    }
    void loadMe();
    return () => {
      cancelled = true;
    };
  }, []);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  const updateUser = async (userId: string, payload: UpdateUserRequest, successMessage: string) => {
    setBusyUserId(userId);
    setError("");
    setMessage("");
    try {
      await apiFetch<UserSummary>(`/admin/users/${userId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      setMessage(successMessage);
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "사용자 수정 실패");
    } finally {
      setBusyUserId(null);
    }
  };

  const resetPassword = async (user: UserSummary) => {
    const password = (passwordDrafts[user.id] || "").trim();
    if (password.length < 8) {
      setError("비밀번호는 8자 이상이어야 합니다.");
      return;
    }

    await updateUser(user.id, { password }, `비밀번호 재설정 완료: ${user.username}`);
    setPasswordDrafts((prev) => ({ ...prev, [user.id]: "" }));
  };

  const createUser = async () => {
    if (!newUsername.trim() || !newPassword.trim()) {
      setError("아이디/비밀번호를 입력하세요.");
      return;
    }

    setCreating(true);
    setError("");
    setMessage("");
    try {
      await apiPost<UserSummary>("/admin/users", {
        username: newUsername.trim(),
        password: newPassword,
        role: newRole,
      });
      setMessage(`사용자 생성 완료: ${newUsername.trim()}`);
      setNewUsername("");
      setNewPassword("");
      setNewRole("VIEWER");
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "사용자 생성 실패");
    } finally {
      setCreating(false);
    }
  };

  const deleteUser = async (user: UserSummary) => {
    if (user.id === currentUserId) {
      setError("현재 로그인한 관리자 계정은 삭제할 수 없습니다.");
      return;
    }

    const ok = window.confirm(`사용자 '${user.username}' 계정을 삭제하시겠습니까?`);
    if (!ok) return;

    setBusyUserId(user.id);
    setError("");
    setMessage("");
    try {
      await apiFetch<DeleteUserResponse>(`/admin/users/${user.id}`, { method: "DELETE" });
      setMessage(`사용자 삭제 완료: ${user.username}`);
      await loadUsers();
    } catch (err) {
      setError(err instanceof Error ? err.message : "사용자 삭제 실패");
    } finally {
      setBusyUserId(null);
    }
  };

  const applySearch = () => {
    setQuery(queryInput);
    setPage(1);
  };

  const clearFilters = () => {
    setQueryInput("");
    setQuery("");
    setRoleFilter("");
    setActiveFilter("");
    setPage(1);
  };

  return (
    <section className="space-y-4">
      <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
        <h2 className="mb-3 inline-flex items-center gap-1 text-sm font-semibold">
          <User className="h-4 w-4 text-accent" />
          사용자 생성
        </h2>
        <div className="grid gap-2 md:grid-cols-[1fr_1fr_180px_auto]">
          <input
            className="rounded border border-stone-300 px-3 py-2 text-sm"
            placeholder="아이디"
            value={newUsername}
            onChange={(e) => setNewUsername(e.target.value)}
          />
          <input
            type="password"
            className="rounded border border-stone-300 px-3 py-2 text-sm"
            placeholder="비밀번호"
            value={newPassword}
            onChange={(e) => setNewPassword(e.target.value)}
          />
          <select
            className="rounded border border-stone-300 px-2 py-2 text-sm"
            value={newRole}
            onChange={(e) => setNewRole(e.target.value as UserRole)}
          >
            {ROLE_OPTIONS.map((role) => (
              <option key={role} value={role}>
                {userRoleLabel(role)}
              </option>
            ))}
          </select>
          <button
            className="inline-flex items-center justify-center gap-1 rounded bg-accent px-3 py-2 text-sm text-white disabled:opacity-60"
            onClick={createUser}
            disabled={creating}
          >
            <Users className="h-4 w-4" />
            {creating ? "생성 중..." : "사용자 생성"}
          </button>
        </div>
      </article>

      <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="inline-flex items-center gap-1 text-sm font-semibold">
            <Users className="h-4 w-4 text-accent" />
            사용자 목록
          </h2>
          <div className="flex gap-1">
            <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50" onClick={applySearch}>
              <Search className="h-3.5 w-3.5" />
              검색 적용
            </button>
            <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50" onClick={clearFilters}>
              <RefreshCcw className="h-3.5 w-3.5" />
              초기화
            </button>
            <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50" onClick={() => void loadUsers()}>
              <RefreshCcw className="h-3.5 w-3.5" />
              새로고침
            </button>
          </div>
        </div>

        <div className="mb-3 grid gap-2 md:grid-cols-[1fr_160px_160px_auto]">
          <input
            className="rounded border border-stone-300 px-3 py-2 text-sm"
            placeholder="아이디 검색"
            value={queryInput}
            onChange={(e) => setQueryInput(e.target.value)}
          />
          <select
            className="rounded border border-stone-300 px-2 py-2 text-sm"
            value={roleFilter}
            onChange={(e) => {
              setRoleFilter((e.target.value as UserRole | "") || "");
              setPage(1);
            }}
          >
            <option value="">역할 전체</option>
            {ROLE_OPTIONS.map((role) => (
              <option key={role} value={role}>
                {userRoleLabel(role)}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-stone-300 px-2 py-2 text-sm"
            value={activeFilter}
            onChange={(e) => {
              setActiveFilter((e.target.value as "" | "true" | "false") || "");
              setPage(1);
            }}
          >
            <option value="">상태 전체</option>
            <option value="true">활성</option>
            <option value="false">비활성</option>
          </select>
          <p className="self-center text-xs text-stone-600">
            총 {total.toLocaleString("ko-KR")}건 | 페이지 {page}/{totalPages}
          </p>
        </div>

        {message ? <p className="mb-2 text-sm text-emerald-700">{message}</p> : null}
        {error ? <p className="mb-2 text-sm text-red-700">{error}</p> : null}
        {loading ? <p className="text-sm text-stone-600">사용자 목록 로딩 중...</p> : null}

        {!loading ? (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead>
                <tr className="border-b border-stone-200 text-stone-500">
                  <th className="py-2">아이디</th>
                  <th className="py-2">권한</th>
                  <th className="py-2">활성</th>
                  <th className="py-2">생성일</th>
                  <th className="py-2">최근 로그인</th>
                  <th className="py-2">작업</th>
                </tr>
              </thead>
              <tbody>
                {users.length === 0 ? (
                  <tr>
                    <td className="py-3 text-stone-600" colSpan={6}>
                      사용자 없음
                    </td>
                  </tr>
                ) : null}

                {users.map((user) => (
                  <tr key={user.id} className="border-b border-stone-100">
                    <td className="py-2 font-medium text-stone-900">{user.username}</td>
                    <td className="py-2">
                      <select
                        className="rounded border border-stone-300 px-2 py-1 text-xs"
                        value={roleDrafts[user.id] ?? user.role}
                        onChange={(e) =>
                          setRoleDrafts((prev) => ({ ...prev, [user.id]: e.target.value as UserRole }))
                        }
                      >
                        {ROLE_OPTIONS.map((role) => (
                          <option key={role} value={role}>
                            {userRoleLabel(role)}
                          </option>
                        ))}
                      </select>
                    </td>
                    <td className="py-2">{user.is_active ? "활성" : "비활성"}</td>
                    <td className="py-2 text-xs text-stone-600">{formatDateTime(user.created_at)}</td>
                    <td className="py-2 text-xs text-stone-600">{formatDateTime(user.last_login_at)}</td>
                    <td className="py-2">
                      <div className="flex flex-wrap gap-1">
                        <button
                          className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50 disabled:opacity-50"
                          disabled={busyUserId === user.id || roleDrafts[user.id] === user.role}
                          onClick={() =>
                            void updateUser(
                              user.id,
                              { role: roleDrafts[user.id] ?? user.role },
                              `역할 변경 완료: ${user.username}`,
                            )
                          }
                        >
                          역할 저장
                        </button>
                        <button
                          className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50 disabled:opacity-50"
                          disabled={busyUserId === user.id}
                          onClick={() =>
                            void updateUser(
                              user.id,
                              { is_active: !user.is_active },
                              `${user.username} ${user.is_active ? "비활성화" : "활성화"} 완료`,
                            )
                          }
                        >
                          {user.is_active ? "비활성화" : "활성화"}
                        </button>
                        <input
                          type="password"
                          className="rounded border border-stone-300 px-2 py-1 text-xs"
                          placeholder="새 비밀번호(8+)"
                          value={passwordDrafts[user.id] ?? ""}
                          onChange={(e) =>
                            setPasswordDrafts((prev) => ({
                              ...prev,
                              [user.id]: e.target.value,
                            }))
                          }
                        />
                        <button
                          className="rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50 disabled:opacity-50"
                          disabled={busyUserId === user.id || !(passwordDrafts[user.id] || "").trim()}
                          onClick={() => void resetPassword(user)}
                        >
                          비밀번호 재설정
                        </button>
                        <button
                          className="rounded border border-red-300 px-2 py-1 text-xs text-red-700 hover:bg-red-50 disabled:opacity-50"
                          disabled={busyUserId === user.id || user.id === currentUserId}
                          onClick={() => void deleteUser(user)}
                          title={user.id === currentUserId ? "현재 로그인 사용자 삭제 불가" : "사용자 삭제"}
                        >
                          계정 삭제
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </article>

      <div className="flex justify-end gap-2">
        <button
          className="rounded border border-stone-300 px-3 py-1 text-sm disabled:opacity-50"
          onClick={() => setPage((p) => Math.max(1, p - 1))}
          disabled={page <= 1}
        >
          이전
        </button>
        <button
          className="rounded border border-stone-300 px-3 py-1 text-sm disabled:opacity-50"
          onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
          disabled={page >= totalPages}
        >
          다음
        </button>
      </div>
    </section>
  );
}
