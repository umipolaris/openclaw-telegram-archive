"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { Files, FolderTree, RefreshCcw, Search, Tag } from "lucide-react";

import { apiGet } from "@/lib/api-client";
import { reviewStatusLabel } from "@/lib/labels";

type ReviewStatus = "NONE" | "NEEDS_REVIEW" | "RESOLVED";

type ArchiveSetRevisionItem = {
  document_id: string;
  title: string;
  category: string | null;
  event_date: string | null;
  ingested_at: string;
  review_status: ReviewStatus;
  file_count: number;
  tags: string[];
  revision: string | null;
  kind: string | null;
  language: string | null;
  source_ref: string | null;
};

type ArchiveSetDocumentNode = {
  document_key: string;
  display_title: string;
  latest_event_date: string | null;
  revision_count: number;
  needs_review_count: number;
  kinds: string[];
  revisions: ArchiveSetRevisionItem[];
  has_more_revisions: boolean;
};

type ArchiveSetNode = {
  set_key: string;
  set_label: string;
  latest_event_date: string | null;
  document_count: number;
  revision_count: number;
  needs_review_count: number;
  documents: ArchiveSetDocumentNode[];
  has_more_documents: boolean;
};

type ArchiveSetsResponse = {
  items: ArchiveSetNode[];
  page: number;
  size: number;
  total_sets: number;
  generated_at: string;
  truncated: boolean;
  max_documents_scanned: number;
};

const PAGE_SIZE = 10;
const DOCUMENT_LIMIT = 40;
const REVISION_LIMIT = 10;

function formatDate(value: string | null): string {
  if (!value) return "-";
  return value;
}

function formatDateTime(value: string): string {
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? "-" : dt.toLocaleString("ko-KR");
}

function reviewClassName(status: ReviewStatus): string {
  if (status === "NEEDS_REVIEW") return "border-red-300 bg-red-50 text-red-700";
  if (status === "RESOLVED") return "border-emerald-300 bg-emerald-50 text-emerald-700";
  return "border-stone-300 bg-stone-50 text-stone-700";
}

export function ArchiveSetWorkspace() {
  const [queryInput, setQueryInput] = useState("");
  const [query, setQuery] = useState("");
  const [includeUnmapped, setIncludeUnmapped] = useState(true);
  const [page, setPage] = useState(1);

  const [items, setItems] = useState<ArchiveSetNode[]>([]);
  const [totalSets, setTotalSets] = useState(0);
  const [truncated, setTruncated] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const [selectedSetKey, setSelectedSetKey] = useState<string | null>(null);

  const totalPages = useMemo(() => Math.max(1, Math.ceil(totalSets / PAGE_SIZE)), [totalSets]);
  const selectedSet = useMemo(() => items.find((item) => item.set_key === selectedSetKey) ?? null, [items, selectedSetKey]);

  useEffect(() => {
    let cancelled = false;

    async function loadSets() {
      setLoading(true);
      setError("");
      try {
        const params = new URLSearchParams();
        params.set("page", String(page));
        params.set("size", String(PAGE_SIZE));
        params.set("document_limit", String(DOCUMENT_LIMIT));
        params.set("revision_limit", String(REVISION_LIMIT));
        params.set("include_unmapped", includeUnmapped ? "true" : "false");
        if (query.trim()) params.set("q", query.trim());

        const res = await apiGet<ArchiveSetsResponse>(`/archive/sets?${params.toString()}`);
        if (cancelled) return;

        setItems(res.items);
        setTotalSets(res.total_sets);
        setTruncated(res.truncated);
        setSelectedSetKey((prev) => {
          if (prev && res.items.some((item) => item.set_key === prev)) return prev;
          return res.items[0]?.set_key ?? null;
        });
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "세트 로드 실패");
          setItems([]);
          setTotalSets(0);
          setSelectedSetKey(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    void loadSets();
    return () => {
      cancelled = true;
    };
  }, [includeUnmapped, page, query]);

  const applyQuery = () => {
    setQuery(queryInput);
    setPage(1);
  };

  const clearQuery = () => {
    setQueryInput("");
    setQuery("");
    setPage(1);
  };

  return (
    <div className="space-y-4">
      <article className="rounded-lg border border-stone-200 bg-panel p-3 shadow-panel">
        <h3 className="mb-2 inline-flex items-center gap-1 text-sm font-semibold">
          <Tag className="h-4 w-4 text-accent" />
          운영 권장 태그 구조
        </h3>
        <p className="text-xs text-stone-700">
          캡션의 <code>#태그</code>에 구조화 키를 넣으면 세트/개정 화면이 자동으로 정리됩니다.
        </p>
        <div className="mt-2 grid gap-2 text-xs text-stone-700 md:grid-cols-2">
          <p>
            <span className="font-semibold">문서 세트:</span> <code>set:dcp</code>
          </p>
          <p>
            <span className="font-semibold">문서 키:</span> <code>dockey:document-control-procedure</code>
          </p>
          <p>
            <span className="font-semibold">개정:</span> <code>rev:2</code>
          </p>
          <p>
            <span className="font-semibold">종류:</span> <code>kind:main</code>, <code>kind:manual</code>
          </p>
        </div>
      </article>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-12">
        <article className="rounded-lg border border-stone-200 bg-panel p-3 shadow-panel lg:col-span-4">
          <h3 className="mb-2 inline-flex items-center gap-1 text-sm font-semibold">
            <FolderTree className="h-4 w-4 text-accent" />
            세트 목록
          </h3>
          <div className="mb-2 grid gap-2">
            <input
              className="rounded border border-stone-300 px-3 py-2 text-sm"
              placeholder="세트/제목/태그 검색"
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
            />
            <div className="flex items-center gap-2">
              <button className="inline-flex items-center gap-1 rounded bg-accent px-3 py-2 text-xs text-white" onClick={applyQuery}>
                <Search className="h-3.5 w-3.5" />
                검색
              </button>
              <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-2 text-xs hover:bg-stone-50" onClick={clearQuery}>
                <RefreshCcw className="h-3.5 w-3.5" />
                초기화
              </button>
            </div>
            <label className="flex items-center gap-2 text-xs text-stone-700">
              <input
                type="checkbox"
                checked={includeUnmapped}
                onChange={(e) => {
                  setIncludeUnmapped(e.target.checked);
                  setPage(1);
                }}
              />
              세트 미지정 문서 포함
            </label>
          </div>

          <p className="mb-2 text-xs text-stone-600">
            총 {totalSets.toLocaleString("ko-KR")}세트 | 페이지 {page}/{totalPages}
          </p>

          {loading ? <p className="text-sm text-stone-600">세트 로딩 중...</p> : null}
          {error ? <p className="text-sm text-red-700">로드 실패: {error}</p> : null}
          {truncated ? (
            <p className="mb-2 rounded border border-amber-300 bg-amber-50 px-2 py-1 text-xs text-amber-700">
              요청당 스캔 상한으로 일부 문서만 반영되었습니다. 검색어를 더 좁혀주세요.
            </p>
          ) : null}

          <div className="space-y-2">
            {items.length === 0 && !loading && !error ? <p className="text-sm text-stone-600">표시할 세트가 없습니다.</p> : null}
            {items.map((item) => (
              <button
                key={item.set_key}
                className={`w-full rounded border p-2 text-left text-xs transition ${
                  selectedSetKey === item.set_key
                    ? "border-accent bg-accentSoft"
                    : "border-stone-200 bg-white hover:bg-stone-50"
                }`}
                onClick={() => setSelectedSetKey(item.set_key)}
              >
                <p className="text-sm font-semibold text-stone-900">{item.set_label}</p>
                <p className="text-stone-600">
                  문서 {item.document_count} | 리비전 {item.revision_count} | 검토 {item.needs_review_count}
                </p>
                <p className="text-stone-500">최신 이벤트일: {formatDate(item.latest_event_date)}</p>
              </button>
            ))}
          </div>

          <div className="mt-3 flex items-center justify-end gap-2">
            <button
              className="rounded border border-stone-300 px-3 py-1 text-xs disabled:opacity-50"
              onClick={() => setPage((prev) => Math.max(1, prev - 1))}
              disabled={page <= 1}
            >
              이전
            </button>
            <button
              className="rounded border border-stone-300 px-3 py-1 text-xs disabled:opacity-50"
              onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
              disabled={page >= totalPages}
            >
              다음
            </button>
          </div>
        </article>

        <article className="rounded-lg border border-stone-200 bg-panel p-3 shadow-panel lg:col-span-8">
          <h3 className="mb-2 inline-flex items-center gap-1 text-sm font-semibold">
            <Files className="h-4 w-4 text-accent" />
            세트 상세
          </h3>
          {!selectedSet ? <p className="text-sm text-stone-600">좌측에서 세트를 선택하세요.</p> : null}

          {selectedSet ? (
            <div className="space-y-3">
              <div className="rounded border border-stone-200 bg-stone-50 p-3 text-xs text-stone-700">
                <p className="text-sm font-semibold text-stone-900">{selectedSet.set_label}</p>
                <p>
                  문서 {selectedSet.document_count} | 리비전 {selectedSet.revision_count} | 검토 필요 {selectedSet.needs_review_count}
                </p>
                <p>최신 이벤트일: {formatDate(selectedSet.latest_event_date)}</p>
                {selectedSet.has_more_documents ? (
                  <p className="mt-1 text-amber-700">문서 그룹이 많아 상위 {DOCUMENT_LIMIT}개만 표시합니다.</p>
                ) : null}
              </div>

              {selectedSet.documents.length === 0 ? <p className="text-sm text-stone-600">문서 그룹이 없습니다.</p> : null}

              {selectedSet.documents.map((doc) => (
                <section key={`${selectedSet.set_key}:${doc.document_key}`} className="rounded border border-stone-200 p-3">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <div>
                      <p className="text-sm font-semibold text-stone-900">{doc.document_key}</p>
                      <p className="text-xs text-stone-600">
                        리비전 {doc.revision_count} | 검토 {doc.needs_review_count} | 최신 {formatDate(doc.latest_event_date)}
                      </p>
                    </div>
                    <p className="text-xs text-stone-600">종류: {doc.kinds.join(", ") || "-"}</p>
                  </div>

                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-stone-200 text-stone-500">
                          <th className="py-1">날짜</th>
                          <th className="py-1">개정</th>
                          <th className="py-1">종류</th>
                          <th className="py-1">제목</th>
                          <th className="py-1">분류</th>
                          <th className="py-1">파일</th>
                          <th className="py-1">상태</th>
                          <th className="py-1">열기</th>
                        </tr>
                      </thead>
                      <tbody>
                        {doc.revisions.map((revision) => (
                          <tr key={revision.document_id} className="border-b border-stone-100">
                            <td className="py-1">{formatDate(revision.event_date)}</td>
                            <td className="py-1">{revision.revision || "-"}</td>
                            <td className="py-1">{revision.kind || "-"}</td>
                            <td className="py-1">
                              <p className="font-medium text-stone-900">{revision.title}</p>
                              <p className="text-[11px] text-stone-500">수집: {formatDateTime(revision.ingested_at)}</p>
                            </td>
                            <td className="py-1">{revision.category || "미분류"}</td>
                            <td className="py-1">{revision.file_count}</td>
                            <td className="py-1">
                              <span className={`rounded border px-2 py-0.5 ${reviewClassName(revision.review_status)}`}>
                                {reviewStatusLabel(revision.review_status)}
                              </span>
                            </td>
                            <td className="py-1">
                              <Link className="rounded border border-stone-300 px-2 py-1 hover:bg-stone-50" href={`/documents/${revision.document_id}`}>
                                문서
                              </Link>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  {doc.has_more_revisions ? (
                    <p className="mt-2 text-xs text-amber-700">리비전이 많아 상위 {REVISION_LIMIT}개만 표시합니다.</p>
                  ) : null}
                </section>
              ))}
            </div>
          ) : null}
        </article>
      </div>
    </div>
  );
}
