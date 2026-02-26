const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "/api";

export function buildApiUrl(path: string): string {
  return `${API_BASE}${path}`;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(buildApiUrl(path), {
    cache: "no-store",
    credentials: "include",
    ...init,
  });
  if (!res.ok) {
    let detail = "";
    try {
      const body = (await res.json()) as { detail?: unknown };
      const raw = body?.detail;
      if (typeof raw === "string") {
        detail = raw;
      } else if (raw && typeof raw === "object") {
        detail = JSON.stringify(raw);
      } else if (raw != null) {
        detail = String(raw);
      }
    } catch {
      try {
        detail = await res.text();
      } catch {
        detail = "";
      }
    }
    throw new Error(detail ? `API error: ${res.status} ${detail}` : `API error: ${res.status}`);
  }
  return (await res.json()) as T;
}

export async function apiGet<T>(path: string): Promise<T> {
  return apiFetch<T>(path);
}

export async function apiPost<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function apiPatch<T>(path: string, body: unknown): Promise<T> {
  return apiFetch<T>(path, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
}

export async function apiDelete<T>(path: string): Promise<T> {
  return apiFetch<T>(path, {
    method: "DELETE",
  });
}

export async function apiPostForm<T>(path: string, form: FormData): Promise<T> {
  return apiFetch<T>(path, {
    method: "POST",
    body: form,
  });
}
