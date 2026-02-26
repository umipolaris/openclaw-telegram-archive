"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname, useSearchParams } from "next/navigation";
import { CalendarDays, ListFilter, RefreshCcw } from "lucide-react";
import { apiGet } from "@/lib/api-client";

type TimelineBucket = {
  bucket: string;
  count: number;
};

type TimelineResponse = {
  scale: "year" | "quarter" | "month" | "day";
  buckets: TimelineBucket[];
};

const SCALE_OPTIONS: Array<{ value: TimelineResponse["scale"]; label: string }> = [
  { value: "year", label: "연" },
  { value: "quarter", label: "분기" },
  { value: "month", label: "월" },
  { value: "day", label: "일" },
];

function formatDateInput(value: Date): string {
  const yyyy = value.getFullYear();
  const mm = String(value.getMonth() + 1).padStart(2, "0");
  const dd = String(value.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}

function parseScale(value: string | null): TimelineResponse["scale"] {
  if (value === "year" || value === "quarter" || value === "month" || value === "day") {
    return value;
  }
  return "month";
}

export function TimelineViewer() {
  const pathname = usePathname();
  const searchParams = useSearchParams();

  const initialScale = parseScale(searchParams.get("scale"));
  const initialFrom = searchParams.get("from") || "";
  const initialTo = searchParams.get("to") || "";

  const [scale, setScale] = useState<TimelineResponse["scale"]>(initialScale);
  const [fromDate, setFromDate] = useState(initialFrom);
  const [toDate, setToDate] = useState(initialTo);
  const [data, setData] = useState<TimelineResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    setScale(parseScale(searchParams.get("scale")));
    setFromDate(searchParams.get("from") || "");
    setToDate(searchParams.get("to") || "");
  }, [searchParams]);

  const queryString = useMemo(() => {
    const params = new URLSearchParams();
    params.set("scale", scale);
    if (fromDate) params.set("from", fromDate);
    if (toDate) params.set("to", toDate);
    return params.toString();
  }, [scale, fromDate, toDate]);

  useEffect(() => {
    let cancelled = false;

    async function load() {
      setLoading(true);
      setError("");
      try {
        const res = await apiGet<TimelineResponse>(`/timeline?${queryString}`);
        if (!cancelled) {
          setData(res);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "타임라인 로드 실패");
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
  }, [queryString]);

  const maxCount = useMemo(() => {
    if (!data || data.buckets.length === 0) return 0;
    return Math.max(...data.buckets.map((x) => x.count));
  }, [data]);

  const applyFilters = () => {
    const params = new URLSearchParams();
    params.set("scale", scale);
    if (fromDate) params.set("from", fromDate);
    if (toDate) params.set("to", toDate);
    window.location.assign(`${pathname}?${params.toString()}`);
  };

  const setRecent7Days = () => {
    const now = new Date();
    const from = new Date(now);
    from.setDate(now.getDate() - 6);
    setScale("day");
    setFromDate(formatDateInput(from));
    setToDate(formatDateInput(now));
  };

  return (
    <div className="space-y-4">
      <div className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
        <p className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-stone-700">
          <ListFilter className="h-4 w-4 text-accent" />
          타임라인 필터
        </p>
        <div className="mb-3 flex flex-wrap gap-2 text-sm">
          {SCALE_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              className={`rounded px-3 py-1 ${
                scale === opt.value ? "bg-accent text-white" : "border border-stone-300"
              }`}
              onClick={() => setScale(opt.value)}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div className="grid gap-2 md:grid-cols-3">
          <input
            type="date"
            className="rounded border border-stone-300 p-2 text-sm"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
          />
          <input
            type="date"
            className="rounded border border-stone-300 p-2 text-sm"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
          />
          <div className="flex gap-2">
            <button className="inline-flex items-center gap-1 rounded bg-accent px-3 py-2 text-sm text-white" onClick={applyFilters}>
              <ListFilter className="h-4 w-4" />
              적용
            </button>
            <button className="inline-flex items-center gap-1 rounded border border-stone-300 px-3 py-2 text-sm" onClick={setRecent7Days}>
              <CalendarDays className="h-4 w-4" />
              최근 7일
            </button>
          </div>
        </div>
      </div>

      <div className="rounded-lg border border-stone-200 bg-panel p-4 shadow-panel">
        <p className="mb-3 inline-flex items-center gap-1 text-sm font-semibold text-stone-700">
          <RefreshCcw className="h-4 w-4 text-accent" />
          버킷 결과
        </p>
        {loading ? <p className="text-sm text-stone-600">타임라인 로딩 중...</p> : null}
        {!loading && error ? <p className="text-sm text-red-700">타임라인 로드 실패: {error}</p> : null}
        {!loading && !error && data && data.buckets.length === 0 ? (
          <p className="text-sm text-stone-600">조건에 해당하는 데이터가 없습니다.</p>
        ) : null}

        {!loading && !error && data && data.buckets.length > 0 ? (
          <ul className="space-y-2">
            {data.buckets.map((bucket) => {
              const width = maxCount > 0 ? Math.max(4, Math.round((bucket.count / maxCount) * 100)) : 0;
              return (
                <li key={bucket.bucket} className="grid grid-cols-[120px_1fr_80px] items-center gap-3 text-sm">
                  <span className="text-stone-700">{bucket.bucket}</span>
                  <div className="h-3 rounded bg-stone-100">
                    <div className="h-3 rounded bg-accent" style={{ width: `${width}%` }} />
                  </div>
                  <span className="text-right font-medium text-stone-900">{bucket.count.toLocaleString("ko-KR")}</span>
                </li>
              );
            })}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
