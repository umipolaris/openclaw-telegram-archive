"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Check, Loader2, MessageSquare, Pencil, Trash2, X } from "lucide-react";
import { apiDelete, apiGet, apiPatch, apiPost } from "@/lib/api-client";

type DocumentCommentItem = {
  id: string;
  document_id: string;
  content: string;
  created_at: string;
  updated_at: string;
  created_by: string | null;
  created_by_username: string | null;
  is_edited: boolean;
  can_edit: boolean;
  can_delete: boolean;
};

type DocumentCommentListResponse = {
  items: DocumentCommentItem[];
};

type DocumentCommentDeleteResponse = {
  status: string;
  document_id: string;
  comment_id: string;
};

type DocumentCommentsPanelProps = {
  documentId: string;
  compact?: boolean;
  inlineComposer?: boolean;
};

function formatDateTime(value: string): string {
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? "-" : dt.toLocaleString("ko-KR");
}

export function DocumentCommentsPanel({ documentId, compact = false, inlineComposer = false }: DocumentCommentsPanelProps) {
  const [items, setItems] = useState<DocumentCommentItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [newContent, setNewContent] = useState("");
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState("");

  const isEditing = useMemo(() => Boolean(editingId), [editingId]);

  const loadComments = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const res = await apiGet<DocumentCommentListResponse>(`/documents/${documentId}/comments`);
      setItems(res.items ?? []);
    } catch (err) {
      setItems([]);
      setError(err instanceof Error ? err.message : "코멘트 조회 실패");
    } finally {
      setLoading(false);
    }
  }, [documentId]);

  useEffect(() => {
    setNewContent("");
    setEditingId(null);
    setEditingContent("");
    setNotice("");
    void loadComments();
  }, [documentId, loadComments]);

  const submitCreate = async () => {
    const content = newContent.trim();
    if (!content) {
      setError("코멘트 내용을 입력하세요.");
      return;
    }
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      const created = await apiPost<DocumentCommentItem>(`/documents/${documentId}/comments`, { content });
      setItems((prev) => [...prev, created]);
      setNewContent("");
      setNotice("코멘트가 등록되었습니다.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "코멘트 등록 실패");
    } finally {
      setSubmitting(false);
    }
  };

  const startEdit = (item: DocumentCommentItem) => {
    setEditingId(item.id);
    setEditingContent(item.content);
    setError("");
    setNotice("");
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditingContent("");
  };

  const submitEdit = async () => {
    if (!editingId) return;
    const content = editingContent.trim();
    if (!content) {
      setError("코멘트 내용을 입력하세요.");
      return;
    }
    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      const updated = await apiPatch<DocumentCommentItem>(`/documents/${documentId}/comments/${editingId}`, { content });
      setItems((prev) => prev.map((row) => (row.id === updated.id ? updated : row)));
      setEditingId(null);
      setEditingContent("");
      setNotice("코멘트가 수정되었습니다.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "코멘트 수정 실패");
    } finally {
      setSubmitting(false);
    }
  };

  const removeComment = async (item: DocumentCommentItem) => {
    const confirmed = window.confirm("코멘트를 삭제하시겠습니까?");
    if (!confirmed) return;

    setSubmitting(true);
    setError("");
    setNotice("");
    try {
      await apiDelete<DocumentCommentDeleteResponse>(`/documents/${documentId}/comments/${item.id}`);
      setItems((prev) => prev.filter((row) => row.id !== item.id));
      if (editingId === item.id) {
        setEditingId(null);
        setEditingContent("");
      }
      setNotice("코멘트가 삭제되었습니다.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "코멘트 삭제 실패");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className={`rounded border border-stone-200 ${compact ? "bg-white p-2" : "bg-white p-3"}`}>
      <div className="mb-2 inline-flex items-center gap-1 text-xs font-semibold text-stone-700">
        <MessageSquare className="h-3.5 w-3.5" />
        코멘트
      </div>

      {inlineComposer ? (
        <div className="flex items-center gap-2">
          <input
            className="h-8 w-full rounded border border-stone-300 px-2 py-1 text-xs"
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey && !submitting) {
                e.preventDefault();
                void submitCreate();
              }
            }}
            placeholder="한 줄 코멘트 입력"
            disabled={submitting}
          />
          <button
            className="inline-flex h-8 shrink-0 items-center gap-1 rounded border border-emerald-600 bg-emerald-600 px-2 py-1 text-[11px] text-white hover:bg-emerald-700 disabled:opacity-50"
            onClick={() => void submitCreate()}
            disabled={submitting}
            type="button"
          >
            {submitting && !isEditing ? <Loader2 className="h-3 w-3 animate-spin" /> : null}
            등록
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          <textarea
            className={`${compact ? "min-h-16 text-xs" : "min-h-20 text-sm"} w-full rounded border border-stone-300 px-2 py-1`}
            value={newContent}
            onChange={(e) => setNewContent(e.target.value)}
            placeholder="간단한 코멘트를 입력하세요."
            disabled={submitting}
          />
          <div className="flex items-center justify-between gap-2">
            <p className="text-[11px] text-stone-500">최대 2000자</p>
            <button
              className="inline-flex items-center gap-1 rounded border border-emerald-600 bg-emerald-600 px-2 py-1 text-xs text-white hover:bg-emerald-700 disabled:opacity-50"
              onClick={() => void submitCreate()}
              disabled={submitting}
              type="button"
            >
              {submitting && !isEditing ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
              코멘트 등록
            </button>
          </div>
        </div>
      )}

      {loading ? <p className="mt-2 text-xs text-stone-600">코멘트 로딩 중...</p> : null}
      {error ? <p className="mt-2 text-xs text-red-700">코멘트 오류: {error}</p> : null}
      {notice ? <p className="mt-2 text-xs text-emerald-700">{notice}</p> : null}

      <ul className="mt-2 space-y-2">
        {!loading && items.length === 0 ? <li className="text-xs text-stone-500">등록된 코멘트가 없습니다.</li> : null}
        {items.map((item) => {
          const rowEditing = editingId === item.id;
          return (
            <li key={item.id} className="rounded border border-stone-200 bg-stone-50 p-2">
              <div className="mb-1 flex items-center justify-between gap-2">
                <p className="text-[11px] text-stone-600">
                  {item.created_by_username || "알 수 없음"} | {formatDateTime(item.created_at)}
                  {item.is_edited ? ` | 수정 ${formatDateTime(item.updated_at)}` : ""}
                </p>
                <div className="flex items-center gap-1">
                  {item.can_edit ? (
                    <button
                      className="inline-flex items-center gap-1 rounded border border-stone-300 px-1.5 py-0.5 text-[11px] text-stone-700 hover:bg-stone-100 disabled:opacity-50"
                      onClick={() => (rowEditing ? cancelEdit() : startEdit(item))}
                      disabled={submitting}
                      type="button"
                    >
                      {rowEditing ? <X className="h-3 w-3" /> : <Pencil className="h-3 w-3" />}
                      {rowEditing ? "취소" : "수정"}
                    </button>
                  ) : null}
                  {item.can_delete ? (
                    <button
                      className="inline-flex items-center gap-1 rounded border border-red-300 px-1.5 py-0.5 text-[11px] text-red-700 hover:bg-red-50 disabled:opacity-50"
                      onClick={() => void removeComment(item)}
                      disabled={submitting}
                      type="button"
                    >
                      <Trash2 className="h-3 w-3" />
                      삭제
                    </button>
                  ) : null}
                </div>
              </div>
              {rowEditing ? (
                <div className="space-y-1">
                  <textarea
                    className="min-h-16 w-full rounded border border-stone-300 bg-white px-2 py-1 text-xs"
                    value={editingContent}
                    onChange={(e) => setEditingContent(e.target.value)}
                    disabled={submitting}
                  />
                  <button
                    className="inline-flex items-center gap-1 rounded border border-blue-600 bg-blue-600 px-2 py-1 text-xs text-white hover:bg-blue-700 disabled:opacity-50"
                    onClick={() => void submitEdit()}
                    disabled={submitting}
                    type="button"
                  >
                    {submitting ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Check className="h-3.5 w-3.5" />}
                    수정 저장
                  </button>
                </div>
              ) : (
                <p className={`${compact ? "text-xs" : "text-sm"} whitespace-pre-wrap break-words text-stone-800`}>{item.content}</p>
              )}
            </li>
          );
        })}
      </ul>
    </section>
  );
}
