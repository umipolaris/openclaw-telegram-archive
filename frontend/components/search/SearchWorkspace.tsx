"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Bookmark,
  ChevronLeft,
  ChevronRight,
  RotateCcw,
  Save,
  Search,
  SlidersHorizontal,
  Trash2,
} from "lucide-react";
import { apiFetch, apiGet, apiPost } from "@/lib/api-client";
import type { ApiDocumentListResponse } from "@/lib/api-contract";
import { VirtualizedList } from "@/components/common/VirtualizedList";
import { StatusBadge } from "@/components/common/StatusBadge";
import { reviewStatusLabel } from "@/lib/labels";

type ReviewStatus = "NONE" | "NEEDS_REVIEW" | "RESOLVED";
type DocumentSortBy = "event_date" | "ingested_at" | "created_at" | "title";
type SortOrder = "desc" | "asc";

type DocumentListItem = {
  id: string;
  title: string;
  description: string;
  category: string | null;
  event_date: string | null;
  ingested_at: string;
  tags: string[];
  file_count: number;
  review_status: ReviewStatus;
};

type DocumentListResponse = ApiDocumentListResponse;

type ArchiveCategoryNode = {
  category: string;
};

type ArchiveTreeResponse = {
  categories: ArchiveCategoryNode[];
};

type SavedFilterSummary = {
  id: string;
  user_id: string;
  username: string;
  name: string;
  filter_json: Record<string, unknown>;
  is_shared: boolean;
  is_owner: boolean;
  created_at: string;
  updated_at: string;
};

type SavedFiltersListResponse = {
  items: SavedFilterSummary[];
  page: number;
  size: number;
  total: number;
};

type SearchFilters = {
  q: string;
  category_name: string;
  tag: string;
  review_status: ReviewStatus | "";
  event_date_from: string;
  event_date_to: string;
  sort_by: DocumentSortBy;
  sort_order: SortOrder;
};

const DEFAULT_PAGE_SIZE = 50;
const REVIEW_STATUS_OPTIONS: Array<{ value: SearchFilters["review_status"]; label: string }> = [
  { value: "", label: "전체" },
  { value: "NONE", label: reviewStatusLabel("NONE") },
  { value: "NEEDS_REVIEW", label: reviewStatusLabel("NEEDS_REVIEW") },
  { value: "RESOLVED", label: reviewStatusLabel("RESOLVED") },
];
const SORT_BY_OPTIONS: Array<{ value: DocumentSortBy; label: string }> = [
  { value: "event_date", label: "문서시점" },
  { value: "ingested_at", label: "수집시점" },
  { value: "created_at", label: "생성시점" },
  { value: "title", label: "제목" },
];
const SORT_ORDER_OPTIONS: Array<{ value: SortOrder; label: string }> = [
  { value: "desc", label: "내림차순" },
  { value: "asc", label: "오름차순" },
];

type SearchTemplate = {
  id: string;
  name: string;
  description: string;
  build: () => SearchFilters;
};

function emptyFilters(): SearchFilters {
  return {
    q: "",
    category_name: "",
    tag: "",
    review_status: "",
    event_date_from: "",
    event_date_to: "",
    sort_by: "event_date",
    sort_order: "desc",
  };
}

function buildFilterPayload(filters: SearchFilters): Record<string, string> {
  const payload: Record<string, string> = {};
  if (filters.q.trim()) payload.q = filters.q.trim();
  if (filters.category_name) payload.category_name = filters.category_name;
  if (filters.tag.trim()) payload.tag = filters.tag.trim();
  if (filters.review_status) payload.review_status = filters.review_status;
  if (filters.event_date_from) payload.event_date_from = filters.event_date_from;
  if (filters.event_date_to) payload.event_date_to = filters.event_date_to;
  payload.sort_by = filters.sort_by;
  payload.sort_order = filters.sort_order;
  return payload;
}

function buildDocumentQuery(filters: SearchFilters, page: number, pageSize: number): string {
  const params = new URLSearchParams();
  params.set("page", String(page));
  params.set("size", String(pageSize));

  const payload = buildFilterPayload(filters);
  for (const [key, value] of Object.entries(payload)) {
    params.set(key, value);
  }

  return params.toString();
}

function parseReviewStatus(value: unknown): SearchFilters["review_status"] {
  if (value === "NONE" || value === "NEEDS_REVIEW" || value === "RESOLVED") return value;
  return "";
}

function parseSortBy(value: unknown): DocumentSortBy {
  if (value === "event_date" || value === "ingested_at" || value === "created_at" || value === "title") return value;
  return "event_date";
}

function parseSortOrder(value: unknown): SortOrder {
  if (value === "asc" || value === "desc") return value;
  return "desc";
}

function fromFilterJson(filterJson: Record<string, unknown>): SearchFilters {
  return {
    q: typeof filterJson.q === "string" ? filterJson.q : "",
    category_name: typeof filterJson.category_name === "string" ? filterJson.category_name : "",
    tag: typeof filterJson.tag === "string" ? filterJson.tag : "",
    review_status: parseReviewStatus(filterJson.review_status),
    event_date_from: typeof filterJson.event_date_from === "string" ? filterJson.event_date_from : "",
    event_date_to: typeof filterJson.event_date_to === "string" ? filterJson.event_date_to : "",
    sort_by: parseSortBy(filterJson.sort_by),
    sort_order: parseSortOrder(filterJson.sort_order),
  };
}

function formatDateTime(value: string): string {
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? "-" : dt.toLocaleString("ko-KR");
}

function isoDateBefore(days: number): string {
  const dt = new Date();
  dt.setDate(dt.getDate() - days);
  const y = dt.getFullYear();
  const m = String(dt.getMonth() + 1).padStart(2, "0");
  const d = String(dt.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

export function SearchWorkspace() {
  const [draftFilters, setDraftFilters] = useState<SearchFilters>(() => emptyFilters());
  const [appliedFilters, setAppliedFilters] = useState<SearchFilters>(() => emptyFilters());
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(DEFAULT_PAGE_SIZE);
  const [items, setItems] = useState<DocumentListItem[]>([]);
  const [total, setTotal] = useState(0);
  const [docLoading, setDocLoading] = useState(false);
  const [docError, setDocError] = useState("");

  const [categories, setCategories] = useState<string[]>([]);
  const [savedFilters, setSavedFilters] = useState<SavedFilterSummary[]>([]);
  const [savedLoading, setSavedLoading] = useState(false);
  const [savedError, setSavedError] = useState("");
  const [savedMessage, setSavedMessage] = useState("");
  const [saveName, setSaveName] = useState("");
  const [saveShared, setSaveShared] = useState(false);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(total / pageSize)), [pageSize, total]);
  const quickTemplates = useMemo<SearchTemplate[]>(
    () => [
      {
        id: "needs-review",
        name: "검토 필요",
        description: "검토가 필요한 문서만 조회",
        build: () => ({
          ...emptyFilters(),
          review_status: "NEEDS_REVIEW",
          sort_by: "ingested_at",
          sort_order: "desc",
        }),
      },
      {
        id: "recent-7days",
        name: "최근 7일",
        description: "최근 7일 문서시점 문서",
        build: () => ({
          ...emptyFilters(),
          event_date_from: isoDateBefore(7),
          sort_by: "event_date",
          sort_order: "desc",
        }),
      },
      {
        id: "dcp-docs",
        name: "DCP 문서",
        description: "DCP 키워드 중심 검색",
        build: () => ({
          ...emptyFilters(),
          q: "Document Control Procedure DCP",
          sort_by: "event_date",
          sort_order: "desc",
        }),
      },
      {
        id: "errors-first",
        name: "오류 우선",
        description: "오류/검토 이슈 우선 정렬",
        build: () => ({
          ...emptyFilters(),
          review_status: "NEEDS_REVIEW",
          sort_by: "created_at",
          sort_order: "desc",
        }),
      },
    ],
    [],
  );

  const loadSavedFilters = useCallback(async () => {
    setSavedLoading(true);
    setSavedError("");
    try {
      const res = await apiGet<SavedFiltersListResponse>("/saved-filters?page=1&size=200&include_shared=true");
      setSavedFilters(res.items);
    } catch (err) {
      setSavedError(err instanceof Error ? err.message : "저장된 필터 로드 실패");
    } finally {
      setSavedLoading(false);
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadInitial() {
      setSavedLoading(true);
      setSavedError("");
      try {
        const [tree, filters] = await Promise.all([
          apiGet<ArchiveTreeResponse>("/archive/tree"),
          apiGet<SavedFiltersListResponse>("/saved-filters?page=1&size=200&include_shared=true"),
        ]);
        if (cancelled) return;

        setCategories(Array.from(new Set(tree.categories.map((x) => x.category))).sort((a, b) => a.localeCompare(b, "ko-KR")));
        setSavedFilters(filters.items);
      } catch (err) {
        if (!cancelled) {
          setSavedError(err instanceof Error ? err.message : "초기 데이터 로드 실패");
        }
      } finally {
        if (!cancelled) {
          setSavedLoading(false);
        }
      }
    }

    void loadInitial();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;

    async function loadDocuments() {
      setDocLoading(true);
      setDocError("");
      try {
        const query = buildDocumentQuery(appliedFilters, page, pageSize);
        const res = await apiGet<DocumentListResponse>(`/documents?${query}`);
        if (cancelled) return;
        setItems(
          (res.items || []).map((item) => ({
            id: item.id,
            title: item.title,
            description: item.description || "",
            category: item.category ?? null,
            event_date: item.event_date ?? null,
            ingested_at: item.ingested_at,
            tags: item.tags ?? [],
            file_count: item.file_count ?? 0,
            review_status: item.review_status ?? "NONE",
          })),
        );
        setTotal(res.total);
      } catch (err) {
        if (!cancelled) {
          setDocError(err instanceof Error ? err.message : "문서 조회 실패");
          setItems([]);
          setTotal(0);
        }
      } finally {
        if (!cancelled) {
          setDocLoading(false);
        }
      }
    }

    void loadDocuments();
    return () => {
      cancelled = true;
    };
  }, [appliedFilters, page, pageSize]);

  const applyDraft = () => {
    setAppliedFilters({ ...draftFilters });
    setPage(1);
  };

  const clearFilters = () => {
    const empty = emptyFilters();
    setDraftFilters(empty);
    setAppliedFilters(empty);
    setPage(1);
  };

  const applyTemplate = (template: SearchTemplate) => {
    const built = template.build();
    setDraftFilters(built);
    setAppliedFilters(built);
    setPage(1);
    setSavedMessage(`템플릿 적용: ${template.name}`);
    setSavedError("");
  };

  const saveCurrentFilter = async () => {
    const normalizedName = saveName.trim();
    if (!normalizedName) {
      setSavedError("저장 필터 이름을 입력하세요.");
      return;
    }

    setSavedError("");
    setSavedMessage("");
    try {
      await apiPost<SavedFilterSummary>("/saved-filters", {
        name: normalizedName,
        filter_json: buildFilterPayload(draftFilters),
        is_shared: saveShared,
      });
      setSaveName("");
      setSaveShared(false);
      setSavedMessage(`저장 필터 생성 완료: ${normalizedName}`);
      await loadSavedFilters();
    } catch (err) {
      setSavedError(err instanceof Error ? err.message : "저장 필터 생성 실패");
    }
  };

  const applySavedFilter = (savedFilter: SavedFilterSummary) => {
    const parsed = fromFilterJson(savedFilter.filter_json);
    setDraftFilters(parsed);
    setAppliedFilters(parsed);
    setPage(1);
    setSavedMessage(`저장 필터 적용: ${savedFilter.name}`);
  };

  const deleteSavedFilter = async (savedFilter: SavedFilterSummary) => {
    if (!savedFilter.is_owner) return;

    setSavedError("");
    setSavedMessage("");
    try {
      await apiFetch<void>(`/saved-filters/${savedFilter.id}`, { method: "DELETE" });
      setSavedMessage(`저장 필터 삭제 완료: ${savedFilter.name}`);
      await loadSavedFilters();
    } catch (err) {
      setSavedError(err instanceof Error ? err.message : "저장 필터 삭제 실패");
    }
  };

  return (
    <section className="space-y-4">
      <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="inline-flex items-center gap-1 text-sm font-semibold">
            <SlidersHorizontal className="h-4 w-4 text-accent" />
            고급 검색
          </h2>
          <div className="flex gap-1">
            <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50" onClick={applyDraft}>
              <Search className="h-3.5 w-3.5" />
              검색 적용
            </button>
            <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50" onClick={clearFilters}>
              <RotateCcw className="h-3.5 w-3.5" />
              필터 초기화
            </button>
          </div>
        </div>

        <div className="mb-3 flex flex-wrap items-center gap-2">
          {quickTemplates.map((template) => (
            <button
              key={template.id}
              className="rounded border border-stone-300 bg-white px-2 py-1 text-xs text-stone-700 hover:bg-stone-50"
              onClick={() => applyTemplate(template)}
              title={template.description}
              type="button"
            >
              {template.name}
            </button>
          ))}
        </div>

        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-4">
          <input
            className="rounded border border-stone-300 px-3 py-2 text-sm"
            placeholder="키워드"
            value={draftFilters.q}
            onChange={(e) => setDraftFilters((prev) => ({ ...prev, q: e.target.value }))}
          />
          <select
            className="rounded border border-stone-300 px-2 py-2 text-sm"
            value={draftFilters.category_name}
            onChange={(e) => setDraftFilters((prev) => ({ ...prev, category_name: e.target.value }))}
          >
            <option value="">카테고리 전체</option>
            {categories.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-stone-300 px-2 py-2 text-sm"
            value={draftFilters.review_status}
            onChange={(e) =>
              setDraftFilters((prev) => ({
                ...prev,
                review_status: parseReviewStatus(e.target.value),
              }))
            }
          >
            {REVIEW_STATUS_OPTIONS.map((option) => (
              <option key={option.label} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-stone-300 px-2 py-2 text-sm"
            value={draftFilters.sort_by}
            onChange={(e) => setDraftFilters((prev) => ({ ...prev, sort_by: parseSortBy(e.target.value) }))}
          >
            {SORT_BY_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                정렬: {option.label}
              </option>
            ))}
          </select>
          <select
            className="rounded border border-stone-300 px-2 py-2 text-sm"
            value={draftFilters.sort_order}
            onChange={(e) => setDraftFilters((prev) => ({ ...prev, sort_order: parseSortOrder(e.target.value) }))}
          >
            {SORT_ORDER_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
          <input
            className="rounded border border-stone-300 px-3 py-2 text-sm"
            placeholder="태그 슬러그 (예: ebi)"
            value={draftFilters.tag}
            onChange={(e) => setDraftFilters((prev) => ({ ...prev, tag: e.target.value }))}
          />
          <input
            type="date"
            className="rounded border border-stone-300 px-3 py-2 text-sm"
            value={draftFilters.event_date_from}
            onChange={(e) => setDraftFilters((prev) => ({ ...prev, event_date_from: e.target.value }))}
          />
          <input
            type="date"
            className="rounded border border-stone-300 px-3 py-2 text-sm"
            value={draftFilters.event_date_to}
            onChange={(e) => setDraftFilters((prev) => ({ ...prev, event_date_to: e.target.value }))}
          />
        </div>
      </article>

      <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
        <h2 className="mb-3 inline-flex items-center gap-1 text-sm font-semibold">
          <Bookmark className="h-4 w-4 text-accent" />
          저장된 필터
        </h2>
        <div className="mb-3 grid gap-2 md:grid-cols-[1fr_auto_auto]">
          <input
            className="rounded border border-stone-300 px-3 py-2 text-sm"
            placeholder="저장 이름"
            value={saveName}
            onChange={(e) => setSaveName(e.target.value)}
          />
          <label className="flex items-center gap-1 rounded border border-stone-300 px-2 py-2 text-xs text-stone-700">
            <input type="checkbox" checked={saveShared} onChange={(e) => setSaveShared(e.target.checked)} />
            공유
          </label>
          <button className="inline-flex items-center justify-center gap-1 rounded bg-accent px-3 py-2 text-sm text-white disabled:opacity-60" onClick={() => void saveCurrentFilter()}>
            <Save className="h-4 w-4" />
            현재 필터 저장
          </button>
        </div>

        {savedMessage ? <p className="mb-2 text-sm text-emerald-700">{savedMessage}</p> : null}
        {savedError ? <p className="mb-2 text-sm text-red-700">{savedError}</p> : null}
        {savedLoading ? <p className="text-sm text-stone-600">저장 필터 로딩 중...</p> : null}

        {!savedLoading ? (
          <ul className="space-y-2 text-sm">
            {savedFilters.length === 0 ? <li className="text-stone-600">저장된 필터가 없습니다.</li> : null}
            {savedFilters.map((savedFilter) => (
              <li key={savedFilter.id} className="rounded border border-stone-200 p-2">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="font-medium text-stone-900">
                      {savedFilter.name}
                      {savedFilter.is_shared ? " (공유)" : ""}
                    </p>
                    <p className="text-xs text-stone-600">
                      작성자 {savedFilter.username} | 수정: {formatDateTime(savedFilter.updated_at)}
                    </p>
                  </div>
                  <div className="flex gap-1">
                    <button
                      className="inline-flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50"
                      onClick={() => applySavedFilter(savedFilter)}
                    >
                      <Search className="h-3.5 w-3.5" />
                      적용
                    </button>
                    {savedFilter.is_owner ? (
                      <button
                        className="inline-flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50"
                        onClick={() => void deleteSavedFilter(savedFilter)}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                        삭제
                      </button>
                    ) : null}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        ) : null}
      </article>

      <article className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
        <div className="mb-2 flex items-center justify-between">
          <h2 className="inline-flex items-center gap-1 text-sm font-semibold">
            <Search className="h-4 w-4 text-accent" />
            검색 결과 ({total.toLocaleString("ko-KR")}건)
          </h2>
          <div className="flex items-center gap-2">
            <label className="text-xs text-stone-600">페이지 크기</label>
            <select
              className="rounded border border-stone-300 px-2 py-1 text-xs"
              value={pageSize}
              onChange={(e) => {
                const nextSize = Number(e.target.value);
                setPageSize(nextSize);
                setPage(1);
              }}
            >
              {[20, 50, 100, 200].map((size) => (
                <option key={size} value={size}>
                  {size}
                </option>
              ))}
            </select>
            <p className="text-xs text-stone-600">
              페이지 {page}/{totalPages}
            </p>
          </div>
        </div>

        {docError ? <p className="mb-2 text-sm text-red-700">{docError}</p> : null}
        {docLoading ? <p className="text-sm text-stone-600">문서 조회 중...</p> : null}

        {!docLoading ? (
          <div className="rounded border border-stone-200">
            <div className="grid grid-cols-[minmax(220px,2fr)_minmax(120px,1fr)_140px_minmax(180px,1.3fr)_120px] border-b border-stone-200 px-3 py-2 text-xs text-stone-500">
              <span>제목</span>
              <span>분류</span>
              <span>문서시점</span>
              <span>태그</span>
              <span>검토</span>
            </div>
            <VirtualizedList
              items={items}
              rowHeight={84}
              height={520}
              className="bg-white"
              emptyFallback={<p className="px-3 py-3 text-sm text-stone-600">검색 결과가 없습니다.</p>}
              renderRow={(item, _index, style) => (
                <div
                  key={item.id}
                  style={style}
                  className="grid grid-cols-[minmax(220px,2fr)_minmax(120px,1fr)_140px_minmax(180px,1.3fr)_120px] border-b border-stone-100 px-3 py-2 text-sm"
                >
                  <div className="min-w-0">
                    <Link href={`/documents/${item.id}`} className="font-medium text-blue-700 hover:underline">
                      {item.title}
                    </Link>
                    <p className="truncate text-xs text-stone-600">{item.description || "-"}</p>
                  </div>
                  <span className="text-stone-700">{item.category ?? "미분류"}</span>
                  <span className="text-stone-700">{item.event_date ?? "-"}</span>
                  <span className="truncate text-stone-700">{item.tags.join(", ") || "-"}</span>
                  <span className="text-stone-700">
                    <StatusBadge
                      tone={item.review_status === "NEEDS_REVIEW" ? "review" : item.review_status === "RESOLVED" ? "resolved" : "normal"}
                      label={reviewStatusLabel(item.review_status)}
                      compact
                    />
                  </span>
                </div>
              )}
            />
          </div>
        ) : null}

        <div className="mt-3 flex justify-end gap-2">
          <button
            className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-1 text-sm disabled:opacity-50"
            onClick={() => setPage((prev) => Math.max(1, prev - 1))}
            disabled={page <= 1}
          >
            <ChevronLeft className="h-4 w-4" />
            이전
          </button>
          <button
            className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-1 text-sm disabled:opacity-50"
            onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
            disabled={page >= totalPages}
          >
            다음
            <ChevronRight className="h-4 w-4" />
          </button>
        </div>
      </article>
    </section>
  );
}
