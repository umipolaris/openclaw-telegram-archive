"use client";

import { useEffect, useState } from "react";
import type { LucideIcon } from "lucide-react";
import {
  BarChart3,
  CalendarDays,
  ChevronDown,
  ChevronUp,
  CircleAlert,
  Clock3,
  Files,
  FolderOpen,
  ListFilter,
  Pin,
  ShieldCheck,
} from "lucide-react";
import { apiGet } from "@/lib/api-client";
import { reviewStatusLabel } from "@/lib/labels";

type DashboardCategoryCount = {
  category: string;
  count: number;
};

type DashboardErrorCodeCount = {
  error_code: string;
  count: number;
};

type DashboardRecentDocument = {
  id: string;
  title: string;
  category: string;
  event_date: string | null;
  ingested_at: string;
  review_status: "NONE" | "NEEDS_REVIEW" | "RESOLVED";
};

type DashboardSummaryResponse = {
  total_documents: number;
  recent_uploads_7d: number;
  needs_review_count: number;
  failed_jobs_count: number;
  retry_scheduled_count: number;
  dead_letter_count: number;
  failed_error_codes: DashboardErrorCodeCount[];
  categories: DashboardCategoryCount[];
  pinned_by_category?: DashboardPinnedCategory[];
  recent_documents: DashboardRecentDocument[];
  generated_at: string;
};

type DashboardPinnedDocument = {
  id: string;
  title: string;
  category: string;
  event_date: string | null;
  ingested_at: string;
  review_status: "NONE" | "NEEDS_REVIEW" | "RESOLVED";
};

type DashboardPinnedCategory = {
  category: string;
  count: number;
  documents: DashboardPinnedDocument[];
};

function formatDateTime(value: string): string {
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? "-" : dt.toLocaleString("ko-KR");
}

function formatDate(value: Date): string {
  const yyyy = value.getFullYear();
  const mm = String(value.getMonth() + 1).padStart(2, "0");
  const dd = String(value.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

export function DashboardSummary() {
  const [data, setData] = useState<DashboardSummaryResponse | null>(null);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  const [statsOpen, setStatsOpen] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const next = await apiGet<DashboardSummaryResponse>("/dashboard/summary?recent_limit=8");
        if (!cancelled) {
          setData(next);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "대시보드 로드 실패");
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void load();
    return () => {
      cancelled = true;
    };
  }, []);

  if (loading) {
    return <p className="text-sm text-stone-600">대시보드 집계 로딩 중...</p>;
  }

  if (error || !data) {
    return <p className="text-sm text-red-700">대시보드 집계 로드 실패: {error || "unknown"}</p>;
  }

  const now = new Date();
  const from = new Date(now);
  from.setDate(now.getDate() - 6);
  const timelineRecent7dHref = `/timeline?scale=day&from=${encodeURIComponent(formatDate(from))}&to=${encodeURIComponent(formatDate(now))}`;

  const metricCards: Array<{ label: string; value: string; href: string; icon: LucideIcon }> = [
    { label: "총 문서 수", value: data.total_documents.toLocaleString("ko-KR"), href: "/archive", icon: Files },
    { label: "최근 7일 업로드", value: data.recent_uploads_7d.toLocaleString("ko-KR"), href: timelineRecent7dHref, icon: CalendarDays },
    { label: "검토 필요", value: data.needs_review_count.toLocaleString("ko-KR"), href: "/review-queue", icon: ListFilter },
    { label: "실패 작업", value: data.failed_jobs_count.toLocaleString("ko-KR"), href: "/admin", icon: CircleAlert },
    { label: "재시도 대기", value: data.retry_scheduled_count.toLocaleString("ko-KR"), href: "/admin", icon: Clock3 },
    { label: "DLQ", value: data.dead_letter_count.toLocaleString("ko-KR"), href: "/admin", icon: ShieldCheck },
  ];
  const failedErrorCodes = Array.isArray(data.failed_error_codes) ? data.failed_error_codes : [];
  const categories = Array.isArray(data.categories) ? data.categories : [];
  const pinnedByCategory = Array.isArray(data.pinned_by_category) ? data.pinned_by_category : [];
  const recentDocuments = Array.isArray(data.recent_documents) ? data.recent_documents : [];

  return (
    <section className="space-y-4">
      <div className="flex flex-wrap items-center justify-end gap-2">
        <span className="rounded border border-stone-300 bg-white px-2 py-1 text-[11px] text-stone-700">
          총 {data.total_documents.toLocaleString("ko-KR")}
        </span>
        <span className="rounded border border-stone-300 bg-white px-2 py-1 text-[11px] text-stone-700">
          7일 {data.recent_uploads_7d.toLocaleString("ko-KR")}
        </span>
        <span className="rounded border border-stone-300 bg-white px-2 py-1 text-[11px] text-stone-700">
          검토 {data.needs_review_count.toLocaleString("ko-KR")}
        </span>
        <button
          type="button"
          onClick={() => setStatsOpen((prev) => !prev)}
          className="inline-flex items-center gap-1 rounded border border-stone-300 bg-white px-2 py-1 text-xs text-stone-700 hover:bg-stone-50"
        >
          <BarChart3 className="h-3.5 w-3.5" />
          통계
          {statsOpen ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        </button>
      </div>

      {statsOpen ? (
        <div className="space-y-3 rounded-lg border border-stone-200 bg-stone-50 p-3">
          <div className="grid grid-cols-1 gap-3 md:grid-cols-3 lg:grid-cols-6">
            {metricCards.map((card) => (
              <button
                key={card.label}
                type="button"
                onClick={() => window.location.assign(card.href)}
                className="rounded-lg border border-stone-200 bg-panel p-3 text-left shadow-panel transition hover:border-stone-300"
              >
                <p className="inline-flex items-center gap-1 text-xs text-stone-500">
                  <card.icon className="h-3.5 w-3.5" />
                  {card.label}
                </p>
                <p className="mt-1 text-xl font-bold">{card.value}</p>
              </button>
            ))}
          </div>
          <article className="rounded-lg border border-stone-200 bg-panel p-3 shadow-panel">
            <h2 className="inline-flex items-center gap-1 text-sm font-semibold text-stone-700">
              <CircleAlert className="h-4 w-4 text-accent" />
              실패 코드 분포
            </h2>
            <ul className="mt-2 space-y-1.5 text-sm">
              {failedErrorCodes.length === 0 ? <li className="text-stone-500">실패 코드 없음</li> : null}
              {failedErrorCodes.map((item) => (
                <li key={item.error_code} className="flex items-center justify-between gap-2">
                  <span className="font-mono text-xs text-stone-700">{item.error_code}</span>
                  <span className="font-medium text-stone-900">{item.count.toLocaleString("ko-KR")}</span>
                </li>
              ))}
            </ul>
          </article>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
          <h2 className="inline-flex items-center gap-1 text-sm font-semibold text-stone-700">
            <Pin className="h-4 w-4 text-accent" />
            카테고리별 고정글
          </h2>
          <div className="mt-3 space-y-3">
            {pinnedByCategory.length === 0 ? <p className="text-sm text-stone-500">고정글이 없습니다.</p> : null}
            {pinnedByCategory.map((group) => (
              <section key={`pin-${group.category}`} className="rounded border border-stone-200 p-2">
                <p className="mb-1 text-xs font-semibold text-stone-700">
                  {group.category} ({group.count})
                </p>
                <ul className="space-y-1.5">
                  {group.documents.map((doc) => (
                    <li key={`pin-doc-${doc.id}`}>
                      <a
                        href={`/documents/${doc.id}`}
                        className="block rounded border border-stone-200 px-2 py-1.5 text-xs transition hover:border-stone-300"
                      >
                        <p className="font-medium text-stone-900">{doc.title}</p>
                        <p className="text-[11px] text-stone-600">
                          이벤트일: {doc.event_date || "-"} | 상태: {reviewStatusLabel(doc.review_status)}
                        </p>
                      </a>
                    </li>
                  ))}
                </ul>
              </section>
            ))}
          </div>
        </article>

        <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
          <h2 className="inline-flex items-center gap-1 text-sm font-semibold text-stone-700">
            <FolderOpen className="h-4 w-4 text-accent" />
            카테고리별 문서 수
          </h2>
          <ul className="mt-3 space-y-2 text-sm">
            {categories.length === 0 ? <li className="text-stone-500">데이터 없음</li> : null}
            {categories.map((item) => (
              <li key={item.category} className="flex items-center justify-between">
                <span className="text-stone-700">{item.category}</span>
                <span className="font-medium text-stone-900">{item.count.toLocaleString("ko-KR")}</span>
              </li>
            ))}
          </ul>
        </article>

        <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
          <h2 className="inline-flex items-center gap-1 text-sm font-semibold text-stone-700">
            <Files className="h-4 w-4 text-accent" />
            최근 수집 문서
          </h2>
          <ul className="mt-3 space-y-2 text-sm">
            {recentDocuments.length === 0 ? <li className="text-stone-500">데이터 없음</li> : null}
            {recentDocuments.map((doc) => (
              <li key={doc.id}>
                <a href={`/documents/${doc.id}`} className="block rounded border border-stone-200 p-2 transition hover:border-stone-300">
                  <p className="font-medium text-stone-900">{doc.title}</p>
                  <p className="text-xs text-stone-600">
                    {doc.category} | 수집: {formatDateTime(doc.ingested_at)} | 상태: {reviewStatusLabel(doc.review_status)}
                  </p>
                </a>
              </li>
            ))}
          </ul>
        </article>
      </div>

      <div className="flex flex-wrap gap-2 text-sm">
        <a href="/archive" className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-1 hover:bg-stone-50">
          <FolderOpen className="h-4 w-4" />
          아카이브 보기
        </a>
        <a href={timelineRecent7dHref} className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-1 hover:bg-stone-50">
          <CalendarDays className="h-4 w-4" />
          최근 7일 타임라인
        </a>
        <a href="/review-queue" className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-1 hover:bg-stone-50">
          <ListFilter className="h-4 w-4" />
          검토 큐 이동
        </a>
      </div>

      <p className="text-xs text-stone-500">집계 시각: {formatDateTime(data.generated_at)}</p>
    </section>
  );
}
