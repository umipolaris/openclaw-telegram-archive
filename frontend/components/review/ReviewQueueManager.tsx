"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  CalendarCheck2,
  CheckCheck,
  FolderCog,
  ListChecks,
  RefreshCcw,
  SquareCheckBig,
  SquareX,
} from "lucide-react";
import { apiFetch, apiPost } from "@/lib/api-client";

type ReviewItem = {
  document_id: string;
  reasons: string[];
  title: string;
  source_ref: string | null;
  suggested_actions: string[];
};

type ReviewQueueResponse = {
  items: ReviewItem[];
  total: number;
};

async function fetchReviewQueue(): Promise<ReviewQueueResponse> {
  return apiFetch<ReviewQueueResponse>("/review-queue?page=1&size=100");
}

async function bulkUpdate(documentIds: string[], update: Record<string, unknown>) {
  return apiPost<{ requested: number; updated: number; skipped: number }>(
    "/review-queue/bulk",
    { document_ids: documentIds, update },
  );
}

export function ReviewQueueManager() {
  const [items, setItems] = useState<ReviewItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [categoryName, setCategoryName] = useState("");
  const [eventDate, setEventDate] = useState("");
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const selectedIds = useMemo(() => Array.from(selected), [selected]);

  const load = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const data = await fetchReviewQueue();
      setItems(data.items);
      setSelected((prev) => {
        const next = new Set<string>();
        for (const id of prev) {
          if (data.items.some((x) => x.document_id === id)) next.add(id);
        }
        return next;
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "unknown error");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectAll = () => setSelected(new Set(items.map((item) => item.document_id)));
  const clearSelection = () => setSelected(new Set());

  const runBulk = async (update: Record<string, unknown>, successMsg: string) => {
    if (selectedIds.length === 0) {
      setError("선택된 문서가 없습니다.");
      return;
    }

    setBusy(true);
    setError("");
    setMessage("");
    try {
      const result = await bulkUpdate(selectedIds, update);
      setMessage(`${successMsg} (updated=${result.updated}, requested=${result.requested})`);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "bulk action failed");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
        <div className="mb-2 inline-flex items-center gap-1 font-semibold text-amber-900">
          <ListChecks className="h-4 w-4" />
          검토 큐 일괄 작업
        </div>
        <div className="mb-2 flex flex-wrap gap-2">
          <button className="inline-flex items-center gap-1 rounded bg-accent px-3 py-1 text-white disabled:opacity-50" onClick={() => void runBulk({ approve: true }, "일괄 승인 완료")} disabled={busy}>
            <CheckCheck className="h-3.5 w-3.5" />
            선택 승인
          </button>
          <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-1 disabled:opacity-50" onClick={() => void runBulk({ category_name: categoryName }, "카테고리 수정 완료")} disabled={busy || !categoryName.trim()}>
            <FolderCog className="h-3.5 w-3.5" />
            분류 수정
          </button>
          <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-1 disabled:opacity-50" onClick={() => void runBulk({ event_date: eventDate }, "날짜 보정 완료")} disabled={busy || !eventDate}>
            <CalendarCheck2 className="h-3.5 w-3.5" />
            날짜 보정
          </button>
          <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-1" onClick={selectAll}>
            <SquareCheckBig className="h-3.5 w-3.5" />
            전체선택
          </button>
          <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-1" onClick={clearSelection}>
            <SquareX className="h-3.5 w-3.5" />
            선택해제
          </button>
          <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-1" onClick={() => void load()} disabled={loading || busy}>
            <RefreshCcw className="h-3.5 w-3.5" />
            새로고침
          </button>
        </div>
        <div className="grid gap-2 md:grid-cols-2">
          <input
            className="rounded border border-stone-300 p-2"
            placeholder="카테고리명 (예: 회의)"
            value={categoryName}
            onChange={(e) => setCategoryName(e.target.value)}
          />
          <input
            type="date"
            className="rounded border border-stone-300 p-2"
            value={eventDate}
            onChange={(e) => setEventDate(e.target.value)}
          />
        </div>
        <p className="mt-2 inline-flex items-center gap-1 text-stone-700">
          <ListChecks className="h-4 w-4 text-stone-500" />
          선택된 문서: {selectedIds.length}
        </p>
        {message ? <p className="mt-1 text-emerald-700">{message}</p> : null}
        {error ? <p className="mt-1 text-red-700">{error}</p> : null}
      </div>

      <div className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
        {loading ? <p className="text-sm text-stone-600">로딩 중...</p> : null}
        {!loading && items.length === 0 ? <p className="text-sm text-stone-600">검토 필요 문서가 없습니다.</p> : null}
        <ul className="space-y-2 text-sm">
          {items.map((item) => {
            const checked = selected.has(item.document_id);
            return (
              <li key={item.document_id} className="flex items-start gap-2 rounded border border-stone-200 p-2">
                <input type="checkbox" checked={checked} onChange={() => toggle(item.document_id)} className="mt-1" />
                <div>
                  <p className="font-medium">{item.title}</p>
                  <p className="text-stone-600">이유: {item.reasons.join(", ") || "-"}</p>
                  <p className="text-stone-500">source_ref: {item.source_ref ?? "-"}</p>
                </div>
              </li>
            );
          })}
        </ul>
      </div>
    </div>
  );
}
