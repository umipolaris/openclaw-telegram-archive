"use client";

import { FormEvent, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { CheckCircle2, Clock3, Loader2, Send, TriangleAlert, Upload } from "lucide-react";
import { apiGet, apiPostForm } from "@/lib/api-client";

type IngestAcceptedResponse = {
  job_id: string;
  state: string;
  source: string;
  source_ref: string | null;
  queued_at: string;
};

type IngestJobStatusResponse = {
  job_id: string;
  state: string;
  source: string;
  source_ref: string | null;
  document_id: string | null;
  attempt_count: number;
  max_attempts: number;
  last_error_code: string | null;
  last_error_message: string | null;
  received_at: string;
  started_at: string | null;
  finished_at: string | null;
  is_terminal: boolean;
  success: boolean;
};

function toFriendlyApiError(err: unknown, fallback: string): string {
  if (!(err instanceof Error)) return fallback;
  const msg = err.message;
  if (msg.includes("403")) return "권한이 없습니다. EDITOR 또는 ADMIN 계정으로 로그인하세요.";
  if (msg.includes("401")) return "로그인이 만료되었습니다. 다시 로그인하세요.";
  if (msg.includes("404")) return "상태 조회 API가 아직 반영되지 않았습니다. API 서버를 재시작하세요.";
  return msg || fallback;
}

const STATE_LABELS: Record<string, string> = {
  RECEIVED: "접수됨",
  STORED: "파일 저장",
  EXTRACTED: "메타 추출",
  CLASSIFIED: "분류 완료",
  INDEXED: "색인 반영",
  PUBLISHED: "게시 완료",
  NEEDS_REVIEW: "검토 필요",
  FAILED: "실패",
};

function buildCaptionFromSimpleNote(note: string): string | null {
  const trimmed = note.trim();
  if (!trimmed) return null;
  const lines = trimmed
    .split(/\r?\n/g)
    .map((line) => line.trim())
    .filter((line) => line.length > 0);
  if (lines.length === 0) return null;
  if (lines.length === 1) {
    // 설명 1줄만 입력해도 제목이 파일명이 아니라 설명 기반으로 생성되도록 처리
    return `${lines[0]}\n${lines[0]}`;
  }
  return lines.join("\n");
}

function stateTone(state: string): string {
  if (state === "FAILED") return "border-red-200 bg-red-50 text-red-800";
  if (state === "PUBLISHED") return "border-emerald-200 bg-emerald-50 text-emerald-800";
  if (state === "NEEDS_REVIEW") return "border-amber-200 bg-amber-50 text-amber-800";
  return "border-stone-200 bg-stone-50 text-stone-800";
}

type QuickPostComposerProps = {
  compact?: boolean;
  inline?: boolean;
  onQueued?: (result: { jobId: string; state: string }) => void;
  onSuccess?: (result: { jobId: string; documentId: string | null; state: string }) => void;
};

export function QuickPostComposer({ compact = false, inline = false, onQueued, onSuccess }: QuickPostComposerProps) {
  const [file, setFile] = useState<File | null>(null);
  const [note, setNote] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [polling, setPolling] = useState(false);
  const [accepted, setAccepted] = useState<IngestAcceptedResponse | null>(null);
  const [status, setStatus] = useState<IngestJobStatusResponse | null>(null);
  const [error, setError] = useState("");
  const pollingLockRef = useRef(false);
  const completedJobRef = useRef<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  const stateLabel = useMemo(() => {
    const state = status?.state ?? accepted?.state ?? "";
    return STATE_LABELS[state] ?? state;
  }, [accepted?.state, status?.state]);

  const refreshStatus = useCallback(
    async (jobId: string) => {
      if (pollingLockRef.current) return;
      pollingLockRef.current = true;
      try {
        const next = await apiGet<IngestJobStatusResponse>(`/ingest/jobs/${jobId}`);
        setStatus(next);
        if (next.is_terminal) {
          setPolling(false);
          if (next.success && completedJobRef.current !== jobId) {
            completedJobRef.current = jobId;
            onSuccess?.({
              jobId,
              documentId: next.document_id,
              state: next.state,
            });
          }
        }
      } catch (err) {
        setError(toFriendlyApiError(err, "상태 조회 실패"));
        setPolling(false);
      } finally {
        pollingLockRef.current = false;
      }
    },
    [onSuccess],
  );

  useEffect(() => {
    if (!polling || !accepted?.job_id) return;
    const firstTick = window.setTimeout(() => {
      void refreshStatus(accepted.job_id);
    }, 250);
    const timer = window.setInterval(() => {
      void refreshStatus(accepted.job_id);
    }, 2000);
    return () => {
      window.clearTimeout(firstTick);
      window.clearInterval(timer);
    };
  }, [accepted?.job_id, polling, refreshStatus]);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    if (!file) {
      setError("파일 1개를 선택해주세요.");
      return;
    }
    if (!note.trim()) {
      setError("게시 설명은 필수입니다.");
      return;
    }

    setSubmitting(true);
    setError("");
    setAccepted(null);
    setStatus(null);
    completedJobRef.current = null;
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("source", "manual");
      const caption = buildCaptionFromSimpleNote(note);
      if (caption) {
        form.append("caption", caption);
      }

      const res = await apiPostForm<IngestAcceptedResponse>("/ingest/manual", form);
      setAccepted(res);
      setPolling(true);
      onQueued?.({
        jobId: res.job_id,
        state: res.state,
      });
      setFile(null);
      setNote("");
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    } catch (err) {
      setError(toFriendlyApiError(err, "간편게시 등록 실패"));
    } finally {
      setSubmitting(false);
    }
  };

  const wrapperClass = inline
    ? "w-full rounded-md border border-stone-200 bg-panel px-2 py-1.5 shadow-sm"
    : compact
      ? "rounded-md border border-stone-200 bg-panel p-3 shadow-sm"
      : "rounded-lg border border-stone-200 bg-panel p-4 shadow-panel";
  const headingClass = compact
    ? "mb-2 inline-flex items-center gap-1 text-xs font-semibold text-stone-700"
    : "mb-3 inline-flex items-center gap-1 text-sm font-semibold text-stone-700";
  const formClass = inline ? "flex w-full min-w-0 items-center gap-2" : "grid gap-3";
  const fileLabelClass = inline ? "w-56 shrink-0" : "grid gap-1 text-sm";
  const noteLabelClass = inline ? "min-w-0 flex-1" : "grid gap-1 text-sm";
  const fileInputClass = inline
    ? "block w-full rounded border border-stone-300 bg-white px-2 py-1 text-xs file:mr-2 file:rounded file:border-0 file:bg-stone-100 file:px-2 file:py-1 file:text-xs file:font-medium file:text-stone-700 hover:file:bg-stone-200"
    : "rounded border border-stone-300 px-3 py-2";
  const noteInputClass = inline
    ? "h-8 w-full rounded border border-stone-300 px-2 py-1 text-xs"
    : "min-h-24 rounded border border-stone-300 px-3 py-2";
  const submitClass = inline
    ? "inline-flex h-8 shrink-0 items-center justify-center gap-1 rounded bg-accent px-3 text-xs text-white disabled:opacity-60"
    : "inline-flex items-center gap-1 rounded bg-accent px-4 py-2 text-sm text-white disabled:opacity-60";

  return (
    <article className={wrapperClass}>
      {inline ? null : (
        <p className={headingClass}>
          <Upload className="h-4 w-4 text-accent" />
          간편게시
        </p>
      )}
      <form className={formClass} onSubmit={onSubmit}>
        {inline ? (
          <>
            <label className={fileLabelClass}>
              <span className="sr-only">파일 선택</span>
              <input
                ref={fileInputRef}
                className={fileInputClass}
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                required
              />
            </label>
            <label className={noteLabelClass}>
              <span className="sr-only">게시 설명</span>
              <input
                className={noteInputClass}
                type="text"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder="게시 설명 입력 (첫 줄=제목)"
                required
              />
            </label>
            <button type="submit" className={submitClass} disabled={submitting}>
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              {submitting ? "등록중" : "간편게시"}
            </button>
          </>
        ) : (
          <>
            <label className={fileLabelClass}>
              <span className="text-xs font-semibold text-stone-600">파일 1개 *</span>
              <input
                ref={fileInputRef}
                className={fileInputClass}
                type="file"
                onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                required
              />
            </label>

            <label className={noteLabelClass}>
              <span className="text-xs font-semibold text-stone-600">게시 설명 *</span>
              <textarea
                className={noteInputClass}
                value={note}
                onChange={(e) => setNote(e.target.value)}
                placeholder={"첫 줄은 제목으로 사용됩니다.\n2줄 이상이면 1줄=제목, 나머지=설명으로 처리됩니다."}
                required
              />
              <p className="text-xs text-stone-500">설명 1줄만 입력해도 해당 내용 기반으로 제목이 생성됩니다.</p>
            </label>

            <button type="submit" className={submitClass} disabled={submitting}>
              {submitting ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
              {submitting ? "등록중" : "간편게시 실행"}
            </button>
          </>
        )}
      </form>

      {error ? <p className={inline ? "mt-2 text-xs text-red-700" : "mt-3 text-sm text-red-700"}>{error}</p> : null}

      {accepted ? (
        <div
          className={`${inline ? "mt-2 rounded border px-2 py-1.5 text-xs" : "mt-3 rounded border p-3 text-sm"} ${stateTone(status?.state ?? accepted.state)}`}
        >
          <p className={`inline-flex items-center gap-1 ${inline ? "text-xs font-semibold" : "font-medium"}`}>
            {status?.state === "FAILED" ? (
              <TriangleAlert className="h-4 w-4" />
            ) : status?.is_terminal ? (
              <CheckCircle2 className="h-4 w-4" />
            ) : (
              <Clock3 className="h-4 w-4" />
            )}
            처리 상태: {stateLabel}
            {polling ? <Loader2 className="ml-1 h-3.5 w-3.5 animate-spin" /> : null}
          </p>
          <p className={inline ? "mt-1 text-[11px]" : "mt-1 text-xs"}>작업 ID: {accepted.job_id}</p>
          {status?.document_id ? (
            <a className={inline ? "mt-1 inline-block text-[11px] underline" : "mt-2 inline-block text-xs underline"} href={`/documents/${status.document_id}`}>
              {inline ? "문서 상세 이동" : "문서 상세 페이지로 이동"}
            </a>
          ) : null}
          {status?.state === "NEEDS_REVIEW" ? (
            <p className={inline ? "mt-1 text-[11px]" : "mt-1 text-xs"}>검토 큐에서 최종 확인이 필요합니다.</p>
          ) : null}
          {status?.state === "FAILED" ? (
            <p className={inline ? "mt-1 text-[11px]" : "mt-1 text-xs"}>
              오류: {status.last_error_code ?? "UNKNOWN"} {status.last_error_message ? `- ${status.last_error_message}` : ""}
            </p>
          ) : null}
          {accepted?.job_id ? (
            <button
              type="button"
              className={
                inline
                  ? "mt-1 rounded border border-stone-300 bg-white px-2 py-1 text-[11px] hover:bg-stone-100"
                  : "mt-2 rounded border border-stone-300 bg-white px-2 py-1 text-xs hover:bg-stone-100"
              }
              onClick={() => void refreshStatus(accepted.job_id)}
            >
              상태 새로고침
            </button>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}
