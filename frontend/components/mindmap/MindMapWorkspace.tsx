"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  ArrowRight,
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  FileText,
  FolderOpen,
  Minus,
  Plus,
  RotateCcw,
  Search,
  Tags,
} from "lucide-react";
import { apiGet } from "@/lib/api-client";

type MindMapCategoryNode = {
  category: string;
  document_count: number;
  latest_event_date: string | null;
};

type MindMapTagNode = {
  tag: string;
  document_count: number;
  latest_event_date: string | null;
};

type MindMapDocumentNode = {
  id: string;
  title: string;
  category: string;
  event_date: string | null;
  updated_at: string;
  file_count: number;
  tags: string[];
};

type MindMapTreeResponse = {
  generated_at: string;
  selected_category: string | null;
  selected_tag: string | null;
  categories: MindMapCategoryNode[];
  tags: MindMapTagNode[];
  documents: MindMapDocumentNode[];
  page: number;
  size: number;
  total_documents: number;
};

type Point = {
  x: number;
  y: number;
};

type EllipseBounds = {
  x: number;
  y: number;
  rx: number;
  ry: number;
};

type NodeVisual = {
  id: string;
  label: string;
  meta?: string;
  x: number;
  y: number;
  rx: number;
  ry: number;
  fill: string;
  stroke: string;
  strokeWidth?: number;
  labelFontSize: number;
  metaFontSize: number;
  active?: boolean;
  onClick?: () => void;
};

type LayoutCandidate = {
  id: string;
  anchor: Point;
  baseAngle: number;
  baseRadius: number;
  rx: number;
  ry: number;
};

type Weighted = {
  weight: number;
  rx: number;
  ry: number;
  labelFont: number;
  metaFont: number;
};

const PAGE_SIZE = 20;
const VIEWBOX_WIDTH = 1240;
const VIEWBOX_HEIGHT = 760;
const CENTER: Point = { x: VIEWBOX_WIDTH / 2, y: VIEWBOX_HEIGHT / 2 };
const UNTAGGED_LABEL = "(태그없음)";
const CATEGORY_MAX = 12;
const TAG_MAX = 10;
const DOC_MAX = 8;
const ZOOM_MIN = 0.6;
const ZOOM_MAX = 2.0;
const ZOOM_STEP = 0.15;
const COLLISION_PADDING = 18;
const RING_STEP = 30;
const MAX_RINGS = 10;
const ANGLE_OFFSETS = [0, 9, -9, 18, -18, 27, -27, 36, -36, 45, -45, 54, -54, 63, -63, 72, -72];
const NODE_FONT_FAMILY = "'Pretendard Variable', 'Pretendard', 'Noto Sans KR', 'Apple SD Gothic Neo', sans-serif";

const EMPTY_DATA: MindMapTreeResponse = {
  generated_at: new Date(0).toISOString(),
  selected_category: null,
  selected_tag: null,
  categories: [],
  tags: [],
  documents: [],
  page: 1,
  size: PAGE_SIZE,
  total_documents: 0,
};

function formatDate(value: string | null): string {
  return value || "-";
}

function formatDateTime(value: string): string {
  const dt = new Date(value);
  return Number.isNaN(dt.getTime()) ? "-" : dt.toLocaleString("ko-KR");
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function toRad(deg: number): number {
  return (deg * Math.PI) / 180;
}

function polarPoint(origin: Point, radius: number, angleDeg: number): Point {
  return {
    x: origin.x + radius * Math.cos(toRad(angleDeg)),
    y: origin.y + radius * Math.sin(toRad(angleDeg)),
  };
}

function angleBetween(from: Point, to: Point): number {
  return (Math.atan2(to.y - from.y, to.x - from.x) * 180) / Math.PI;
}

function circleAngles(count: number, startDeg = -90): number[] {
  if (count <= 0) return [];
  const step = 360 / count;
  return Array.from({ length: count }, (_, idx) => startDeg + idx * step);
}

function fanAngles(count: number, centerDeg: number, spreadDeg: number): number[] {
  if (count <= 0) return [];
  if (count === 1) return [centerDeg];
  const from = centerDeg - spreadDeg / 2;
  const step = spreadDeg / (count - 1);
  return Array.from({ length: count }, (_, idx) => from + idx * step);
}

function splitLabel(input: string, maxChars = 12, maxLines = 3): string[] {
  const text = input.replace(/\s+/g, " ").trim();
  if (!text) return ["-"];
  const lines: string[] = [];
  for (let i = 0; i < text.length; i += maxChars) {
    lines.push(text.slice(i, i + maxChars));
  }
  if (lines.length <= maxLines) return lines;
  const clipped = lines.slice(0, maxLines);
  const lastIdx = clipped.length - 1;
  clipped[lastIdx] = `${clipped[lastIdx].slice(0, Math.max(1, maxChars - 1))}…`;
  return clipped;
}

function ellipseBoundaryPoint(from: Point, to: Point, rx: number, ry: number): Point {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  if (dx === 0 && dy === 0) return { x: from.x, y: from.y };
  const denom = Math.sqrt((dx * dx) / (rx * rx) + (dy * dy) / (ry * ry));
  const t = denom === 0 ? 0 : 1 / denom;
  return {
    x: from.x + dx * t,
    y: from.y + dy * t,
  };
}

function curvedEdgePath(from: Point, to: Point, bend = 0.11): string {
  const dx = to.x - from.x;
  const dy = to.y - from.y;
  const dist = Math.hypot(dx, dy) || 1;
  const nx = -dy / dist;
  const ny = dx / dist;
  const direction = from.x <= to.x ? 1 : -1;
  const offset = dist * bend * direction;
  const cx = (from.x + to.x) / 2 + nx * offset;
  const cy = (from.y + to.y) / 2 + ny * offset;
  return `M ${from.x} ${from.y} Q ${cx} ${cy} ${to.x} ${to.y}`;
}

function overlaps(a: EllipseBounds, b: EllipseBounds, padding = COLLISION_PADDING): boolean {
  const dx = Math.abs(a.x - b.x);
  const dy = Math.abs(a.y - b.y);
  const normX = dx / (a.rx + b.rx + padding);
  const normY = dy / (a.ry + b.ry + padding);
  return normX * normX + normY * normY < 1;
}

function clampPoint(point: Point, rx: number, ry: number): Point {
  return {
    x: clamp(point.x, rx + 16, VIEWBOX_WIDTH - rx - 16),
    y: clamp(point.y, ry + 16, VIEWBOX_HEIGHT - ry - 16),
  };
}

function placeCandidates(candidates: LayoutCandidate[], occupiedSeed: EllipseBounds[]): Map<string, Point> {
  const positions = new Map<string, Point>();
  const occupied: EllipseBounds[] = [...occupiedSeed];

  for (const candidate of candidates) {
    let placedPoint: Point | null = null;
    let bestPoint: Point | null = null;
    let bestOverlap = Number.POSITIVE_INFINITY;

    for (let ring = 0; ring < MAX_RINGS; ring += 1) {
      const radius = candidate.baseRadius + ring * RING_STEP;
      for (const offset of ANGLE_OFFSETS) {
        const point = clampPoint(
          polarPoint(candidate.anchor, radius, candidate.baseAngle + offset),
          candidate.rx,
          candidate.ry,
        );
        const current: EllipseBounds = { x: point.x, y: point.y, rx: candidate.rx, ry: candidate.ry };
        const overlapCount = occupied.reduce((sum, node) => (overlaps(current, node) ? sum + 1 : sum), 0);

        if (overlapCount === 0) {
          placedPoint = point;
          break;
        }
        if (overlapCount < bestOverlap) {
          bestOverlap = overlapCount;
          bestPoint = point;
        }
      }
      if (placedPoint) break;
    }

    const finalPoint = placedPoint ?? bestPoint ?? clampPoint(polarPoint(candidate.anchor, candidate.baseRadius, candidate.baseAngle), candidate.rx, candidate.ry);
    positions.set(candidate.id, finalPoint);
    occupied.push({ x: finalPoint.x, y: finalPoint.y, rx: candidate.rx, ry: candidate.ry });
  }

  return positions;
}

function normalizeSeries(values: number[]): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (min === max) return values.map(() => 0.5);
  return values.map((value) => (value - min) / (max - min));
}

function weightVisual(weight: number, config: { rxBase: number; rxSpread: number; ryBase: number; rySpread: number; fontBase: number; fontSpread: number }): Weighted {
  const w = clamp(weight, 0, 1);
  return {
    weight: w,
    rx: config.rxBase + config.rxSpread * w,
    ry: config.ryBase + config.rySpread * w,
    labelFont: config.fontBase + config.fontSpread * w,
    metaFont: Math.max(10, config.fontBase - 1 + config.fontSpread * w * 0.45),
  };
}

function prioritizeSelected<T>(items: T[], selected: string | null, max: number, getKey: (item: T) => string): T[] {
  if (items.length <= max) return items;
  if (!selected) return items.slice(0, max);

  const selectedIdx = items.findIndex((item) => getKey(item) === selected);
  if (selectedIdx < 0) return items.slice(0, max);
  if (selectedIdx < max) return items.slice(0, max);

  const picked = items[selectedIdx];
  const rest = items.filter((_, idx) => idx !== selectedIdx).slice(0, max - 1);
  return [picked, ...rest];
}

function MindNode({
  label,
  meta,
  x,
  y,
  rx,
  ry,
  fill,
  stroke,
  strokeWidth = 1.8,
  labelFontSize,
  metaFontSize,
  active = false,
  onClick,
}: NodeVisual) {
  const charsPerLine = clamp(Math.floor(rx / 7) + 5, 8, 13);
  const lines = splitLabel(label, charsPerLine, 2);
  const lineHeight = clamp(labelFontSize + 2, 12, 18);
  const labelBlockHeight = (lines.length - 1) * lineHeight;
  const labelStartY = meta ? -10 - labelBlockHeight / 2 : -labelBlockHeight / 2;

  const handleKeyDown = (event: React.KeyboardEvent<SVGGElement>) => {
    if (!onClick) return;
    if (event.key === "Enter" || event.key === " ") {
      event.preventDefault();
      onClick();
    }
  };

  return (
    <g
      transform={`translate(${x} ${y})`}
      onClick={onClick}
      onKeyDown={handleKeyDown}
      role={onClick ? "button" : undefined}
      tabIndex={onClick ? 0 : -1}
      className={onClick ? "cursor-pointer transition-all duration-200 hover:opacity-95" : undefined}
    >
      <title>{label}</title>
      <ellipse
        rx={rx}
        ry={ry}
        fill={fill}
        stroke={stroke}
        strokeWidth={active ? strokeWidth + 1.2 : strokeWidth}
        filter="url(#node-shadow)"
      />
      <text
        textAnchor="middle"
        y={labelStartY}
        className="pointer-events-none select-none fill-stone-800"
        style={{ fontSize: `${labelFontSize}px`, fontWeight: 700, fontFamily: NODE_FONT_FAMILY }}
      >
        {lines.map((line, idx) => (
          <tspan key={`${label}-${idx}`} x={0} dy={idx === 0 ? 0 : lineHeight}>
            {line}
          </tspan>
        ))}
      </text>
      {meta ? (
        <text
          textAnchor="middle"
          y={ry - 11}
          className="pointer-events-none select-none fill-stone-500"
          style={{ fontSize: `${metaFontSize}px`, fontWeight: 600, fontFamily: NODE_FONT_FAMILY }}
        >
          {meta}
        </text>
      ) : null}
      {active ? <ellipse rx={rx + 6} ry={ry + 6} fill="none" stroke="#38bdf8" strokeOpacity={0.45} strokeWidth={1.8} /> : null}
    </g>
  );
}

export function MindMapWorkspace() {
  const router = useRouter();
  const [queryDraft, setQueryDraft] = useState("");
  const [query, setQuery] = useState("");
  const [selectedCategory, setSelectedCategory] = useState<string | null>(null);
  const [selectedTag, setSelectedTag] = useState<string | null>(null);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<MindMapTreeResponse>(EMPTY_DATA);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [zoomLevel, setZoomLevel] = useState(1);

  const loadTree = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const params = new URLSearchParams();
      params.set("page", String(page));
      params.set("size", String(PAGE_SIZE));
      if (query) params.set("q", query);
      if (selectedCategory) params.set("category_name", selectedCategory);
      if (selectedTag) params.set("tag_name", selectedTag);

      const res = await apiGet<MindMapTreeResponse>(`/mindmap/tree?${params.toString()}`);
      setData(res);
    } catch (err) {
      setData(EMPTY_DATA);
      setError(err instanceof Error ? err.message : "마인드맵 데이터 조회 실패");
    } finally {
      setLoading(false);
    }
  }, [page, query, selectedCategory, selectedTag]);

  useEffect(() => {
    void loadTree();
  }, [loadTree]);

  useEffect(() => {
    if (!selectedCategory && data.categories.length > 0) {
      setSelectedCategory(data.categories[0].category);
      setSelectedTag(null);
      setPage(1);
    }
  }, [data.categories, selectedCategory]);

  useEffect(() => {
    if (selectedTag && !data.tags.some((row) => row.tag === selectedTag)) {
      setSelectedTag(null);
      setPage(1);
    }
  }, [data.tags, selectedTag]);

  const effectiveCategory = selectedCategory ?? data.selected_category;
  const effectiveTag = selectedTag ?? data.selected_tag;
  const totalPages = useMemo(() => Math.max(1, Math.ceil((data.total_documents || 0) / PAGE_SIZE)), [data.total_documents]);

  const mapCategories = useMemo(
    () => prioritizeSelected(data.categories, effectiveCategory, CATEGORY_MAX, (row) => row.category),
    [data.categories, effectiveCategory],
  );
  const mapTags = useMemo(() => prioritizeSelected(data.tags, effectiveTag, TAG_MAX, (row) => row.tag), [data.tags, effectiveTag]);
  const mapDocuments = useMemo(() => data.documents.slice(0, DOC_MAX), [data.documents]);

  const categoryVisualMap = useMemo(() => {
    const weights = normalizeSeries(mapCategories.map((row) => row.document_count));
    const map = new Map<string, Weighted>();
    mapCategories.forEach((row, idx) => {
      map.set(
        row.category,
        weightVisual(weights[idx], {
          rxBase: 72,
          rxSpread: 38,
          ryBase: 42,
          rySpread: 20,
          fontBase: 12,
          fontSpread: 3.2,
        }),
      );
    });
    return map;
  }, [mapCategories]);

  const categoryAngles = useMemo(() => circleAngles(mapCategories.length, -90), [mapCategories.length]);
  const categoryCandidates = useMemo<LayoutCandidate[]>(
    () =>
      mapCategories.map((row, idx) => {
        const visual = categoryVisualMap.get(row.category);
        return {
          id: row.category,
          anchor: CENTER,
          baseAngle: categoryAngles[idx],
          baseRadius: 250,
          rx: visual?.rx ?? 84,
          ry: visual?.ry ?? 46,
        };
      }),
    [categoryAngles, categoryVisualMap, mapCategories],
  );

  const centerEllipse = useMemo<EllipseBounds>(() => ({ x: CENTER.x, y: CENTER.y, rx: 120, ry: 72 }), []);
  const categoryPointMap = useMemo(
    () => placeCandidates(categoryCandidates, [centerEllipse]),
    [categoryCandidates, centerEllipse],
  );

  const categoryNodeMap = useMemo(() => {
    const map = new Map<string, NodeVisual>();
    mapCategories.forEach((row) => {
      const pt = categoryPointMap.get(row.category);
      const visual = categoryVisualMap.get(row.category);
      if (!pt || !visual) return;
      map.set(row.category, {
        id: row.category,
        label: row.category,
        meta: `${row.document_count.toLocaleString("ko-KR")}건`,
        x: pt.x,
        y: pt.y,
        rx: visual.rx,
        ry: visual.ry,
        fill: effectiveCategory === row.category ? "#dbeafe" : "#eef4ff",
        stroke: effectiveCategory === row.category ? "#2563eb" : "#8aa3c2",
        strokeWidth: 2,
        labelFontSize: visual.labelFont,
        metaFontSize: visual.metaFont,
        active: effectiveCategory === row.category,
        onClick: () => {
          setSelectedCategory(row.category);
          setSelectedTag(null);
          setPage(1);
        },
      });
    });
    return map;
  }, [categoryPointMap, categoryVisualMap, mapCategories, effectiveCategory]);

  const selectedCategoryPoint = effectiveCategory ? categoryPointMap.get(effectiveCategory) ?? null : null;
  const selectedCategoryNode = effectiveCategory ? categoryNodeMap.get(effectiveCategory) ?? null : null;

  const tagVisualMap = useMemo(() => {
    const weights = normalizeSeries(mapTags.map((row) => row.document_count));
    const map = new Map<string, Weighted>();
    mapTags.forEach((row, idx) => {
      map.set(
        row.tag,
        weightVisual(weights[idx], {
          rxBase: 64,
          rxSpread: 34,
          ryBase: 36,
          rySpread: 16,
          fontBase: 11,
          fontSpread: 2.8,
        }),
      );
    });
    return map;
  }, [mapTags]);

  const tagCandidates = useMemo<LayoutCandidate[]>(() => {
    if (!selectedCategoryPoint) return [];
    const categoryAngle = angleBetween(CENTER, selectedCategoryPoint);
    const angles = fanAngles(mapTags.length, categoryAngle, 220);
    return mapTags.map((row, idx) => {
      const visual = tagVisualMap.get(row.tag);
      return {
        id: row.tag,
        anchor: selectedCategoryPoint,
        baseAngle: angles[idx],
        baseRadius: 210,
        rx: visual?.rx ?? 78,
        ry: visual?.ry ?? 42,
      };
    });
  }, [selectedCategoryPoint, mapTags, tagVisualMap]);

  const occupiedFromCategories = useMemo<EllipseBounds[]>(() => {
    const list: EllipseBounds[] = [centerEllipse];
    mapCategories.forEach((row) => {
      const node = categoryNodeMap.get(row.category);
      if (node) list.push({ x: node.x, y: node.y, rx: node.rx, ry: node.ry });
    });
    return list;
  }, [categoryNodeMap, mapCategories, centerEllipse]);

  const tagPointMap = useMemo(
    () => placeCandidates(tagCandidates, occupiedFromCategories),
    [occupiedFromCategories, tagCandidates],
  );

  const tagNodeMap = useMemo(() => {
    const map = new Map<string, NodeVisual>();
    mapTags.forEach((row) => {
      const pt = tagPointMap.get(row.tag);
      const visual = tagVisualMap.get(row.tag);
      if (!pt || !visual) return;
      map.set(row.tag, {
        id: row.tag,
        label: row.tag === UNTAGGED_LABEL ? "태그없음" : row.tag,
        meta: `${row.document_count.toLocaleString("ko-KR")}건`,
        x: pt.x,
        y: pt.y,
        rx: visual.rx,
        ry: visual.ry,
        fill: effectiveTag === row.tag ? "#cffafe" : "#ecfeff",
        stroke: effectiveTag === row.tag ? "#0284c7" : "#7cb5d8",
        strokeWidth: 1.9,
        labelFontSize: visual.labelFont,
        metaFontSize: visual.metaFont,
        active: effectiveTag === row.tag,
        onClick: () => {
          setSelectedTag(row.tag);
          setPage(1);
        },
      });
    });
    return map;
  }, [tagPointMap, tagVisualMap, mapTags, effectiveTag]);

  const selectedTagPoint = effectiveTag ? tagPointMap.get(effectiveTag) ?? null : null;
  const selectedTagNode = effectiveTag ? tagNodeMap.get(effectiveTag) ?? null : null;

  const docVisualMap = useMemo(() => {
    const weights = normalizeSeries(mapDocuments.map((row) => Math.log1p(Math.max(1, row.file_count) * 2 + row.tags.length)));
    const map = new Map<string, Weighted>();
    mapDocuments.forEach((row, idx) => {
      map.set(
        row.id,
        weightVisual(weights[idx], {
          rxBase: 70,
          rxSpread: 32,
          ryBase: 34,
          rySpread: 14,
          fontBase: 10.8,
          fontSpread: 2.1,
        }),
      );
    });
    return map;
  }, [mapDocuments]);

  const docCandidates = useMemo<LayoutCandidate[]>(() => {
    if (!selectedTagPoint) return [];
    const baseAngle = selectedCategoryPoint ? angleBetween(selectedCategoryPoint, selectedTagPoint) : -35;
    const angles = fanAngles(mapDocuments.length, baseAngle, 230);
    return mapDocuments.map((row, idx) => {
      const visual = docVisualMap.get(row.id);
      return {
        id: row.id,
        anchor: selectedTagPoint,
        baseAngle: angles[idx],
        baseRadius: 185,
        rx: visual?.rx ?? 82,
        ry: visual?.ry ?? 40,
      };
    });
  }, [selectedCategoryPoint, selectedTagPoint, mapDocuments, docVisualMap]);

  const occupiedFromTag = useMemo<EllipseBounds[]>(() => {
    const list: EllipseBounds[] = [centerEllipse];
    mapCategories.forEach((row) => {
      const node = categoryNodeMap.get(row.category);
      if (node) list.push({ x: node.x, y: node.y, rx: node.rx, ry: node.ry });
    });
    mapTags.forEach((row) => {
      const node = tagNodeMap.get(row.tag);
      if (node) list.push({ x: node.x, y: node.y, rx: node.rx, ry: node.ry });
    });
    return list;
  }, [categoryNodeMap, mapCategories, mapTags, tagNodeMap, centerEllipse]);

  const docPointMap = useMemo(
    () => placeCandidates(docCandidates, occupiedFromTag),
    [docCandidates, occupiedFromTag],
  );

  const docNodeMap = useMemo(() => {
    const map = new Map<string, NodeVisual>();
    mapDocuments.forEach((row) => {
      const pt = docPointMap.get(row.id);
      const visual = docVisualMap.get(row.id);
      if (!pt || !visual) return;
      map.set(row.id, {
        id: row.id,
        label: row.title,
        meta: `${row.file_count}파일`,
        x: pt.x,
        y: pt.y,
        rx: visual.rx,
        ry: visual.ry,
        fill: "#f5f3ff",
        stroke: "#8b7ac5",
        strokeWidth: 1.8,
        labelFontSize: visual.labelFont,
        metaFontSize: visual.metaFont,
        onClick: () => router.push(`/documents/${row.id}`),
      });
    });
    return map;
  }, [docPointMap, docVisualMap, mapDocuments, router]);

  const hiddenCategoryCount = Math.max(0, data.categories.length - mapCategories.length);
  const hiddenTagCount = Math.max(0, data.tags.length - mapTags.length);
  const hiddenDocumentCount = Math.max(0, data.documents.length - mapDocuments.length);

  return (
    <section className="space-y-4">
      <article className="rounded-2xl border border-sky-100 bg-gradient-to-br from-white via-sky-50/45 to-cyan-50/40 p-4 shadow-[0_10px_35px_rgba(2,132,199,0.12)]">
        <div className="flex flex-wrap items-center gap-2 text-sm text-slate-700">
          <span className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-white/90 px-2.5 py-1 text-xs font-medium">
            <FolderOpen className="h-3.5 w-3.5" />
            전체
          </span>
          <ChevronRight className="h-4 w-4 text-sky-400" />
          <span className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-white/90 px-2.5 py-1 text-xs font-medium">
            <Tags className="h-3.5 w-3.5" />
            {effectiveCategory || "카테고리 선택"}
          </span>
          <ChevronRight className="h-4 w-4 text-sky-400" />
          <span className="inline-flex items-center gap-1 rounded-full border border-sky-200 bg-white/90 px-2.5 py-1 text-xs font-medium">
            <FileText className="h-3.5 w-3.5" />
            {effectiveTag || "태그 선택"}
          </span>
        </div>

        <form
          className="mt-3 flex flex-wrap items-center gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            setPage(1);
            setQuery(queryDraft.trim());
          }}
        >
          <label className="flex min-w-[260px] flex-1 items-center gap-2 rounded-xl border border-sky-200 bg-white/95 px-3 py-2 text-sm shadow-sm">
            <Search className="h-4 w-4 text-sky-600" />
            <input
              className="w-full border-none bg-transparent outline-none"
              value={queryDraft}
              onChange={(event) => setQueryDraft(event.target.value)}
              placeholder="제목/설명 검색어"
            />
          </label>
          <button
            className="rounded-xl border border-sky-700 bg-gradient-to-b from-sky-600 to-sky-700 px-3.5 py-2 text-sm font-semibold text-white shadow-sm transition hover:from-sky-500 hover:to-sky-600"
            type="submit"
          >
            반영
          </button>
          <button
            className="inline-flex items-center gap-1 rounded-xl border border-slate-300 bg-white px-3.5 py-2 text-sm font-medium text-slate-700 transition hover:bg-slate-100"
            type="button"
            onClick={() => {
              setQueryDraft("");
              setQuery("");
              setSelectedCategory(null);
              setSelectedTag(null);
              setPage(1);
              setZoomLevel(1);
            }}
          >
            <RotateCcw className="h-3.5 w-3.5" />
            초기화
          </button>
          <p className="text-xs text-slate-500">최근 생성: {formatDateTime(data.generated_at)}</p>
        </form>
      </article>

      {loading ? <p className="text-sm text-stone-600">마인드맵 로딩 중...</p> : null}
      {error ? <p className="text-sm text-red-700">마인드맵 오류: {error}</p> : null}

      <article className="rounded-2xl border border-sky-100 bg-gradient-to-br from-slate-50 via-sky-50/40 to-cyan-50/50 p-4 shadow-[0_14px_38px_rgba(14,116,144,0.14)]">
        <div className="mb-2 flex items-center justify-between">
          <p className="text-sm font-semibold text-slate-800">연관관계 마인드맵</p>
          <div className="flex items-center gap-2">
            <div className="inline-flex items-center rounded-full border border-slate-300 bg-white/90 p-1 shadow-sm">
              <button
                type="button"
                className="inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                onClick={() => setZoomLevel((prev) => clamp(prev - ZOOM_STEP, ZOOM_MIN, ZOOM_MAX))}
                disabled={zoomLevel <= ZOOM_MIN}
                aria-label="마인드맵 축소"
                title="축소"
              >
                <Minus className="h-4 w-4" />
              </button>
              <span className="px-1.5 text-[11px] font-semibold text-slate-600">{Math.round(zoomLevel * 100)}%</span>
              <button
                type="button"
                className="inline-flex h-7 w-7 items-center justify-center rounded-full text-slate-700 transition hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-40"
                onClick={() => setZoomLevel((prev) => clamp(prev + ZOOM_STEP, ZOOM_MIN, ZOOM_MAX))}
                disabled={zoomLevel >= ZOOM_MAX}
                aria-label="마인드맵 확대"
                title="확대"
              >
                <Plus className="h-4 w-4" />
              </button>
            </div>
            <span className="rounded-full border border-white/80 bg-white/85 px-3 py-1 text-[11px] font-semibold text-slate-600 shadow-sm">
              Smart Radial Map
            </span>
          </div>
        </div>
        <div className="overflow-x-auto rounded-2xl border border-sky-100 bg-white/80 shadow-inner">
          <svg viewBox={`0 0 ${VIEWBOX_WIDTH} ${VIEWBOX_HEIGHT}`} className="h-[660px] w-full min-w-[980px]">
            <defs>
              <radialGradient id="map-bg-radial" cx="50%" cy="48%" r="78%">
                <stop offset="0%" stopColor="#ffffff" />
                <stop offset="64%" stopColor="#f3f9ff" />
                <stop offset="100%" stopColor="#e7f3ff" />
              </radialGradient>
              <linearGradient id="edge-cat-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#60a5fa" />
                <stop offset="100%" stopColor="#2563eb" />
              </linearGradient>
              <linearGradient id="edge-tag-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#38bdf8" />
                <stop offset="100%" stopColor="#0284c7" />
              </linearGradient>
              <linearGradient id="edge-doc-grad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" stopColor="#a78bfa" />
                <stop offset="100%" stopColor="#8b5cf6" />
              </linearGradient>
              <filter id="edge-glow" x="-25%" y="-25%" width="150%" height="150%">
                <feGaussianBlur stdDeviation="1.4" result="blurred" />
                <feMerge>
                  <feMergeNode in="blurred" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
              <filter id="node-shadow" x="-30%" y="-30%" width="160%" height="160%">
                <feDropShadow dx="0" dy="2.5" stdDeviation="3" floodColor="#0f172a" floodOpacity="0.18" />
              </filter>
              <marker id="mind-arrow" markerWidth="8" markerHeight="8" refX="7" refY="3.5" orient="auto">
                <path d="M0,0 L0,7 L7,3.5 z" fill="#6382a7" />
              </marker>
            </defs>
            <g transform={`translate(${CENTER.x} ${CENTER.y}) scale(${zoomLevel}) translate(${-CENTER.x} ${-CENTER.y})`}>
              <rect x={0} y={0} width={VIEWBOX_WIDTH} height={VIEWBOX_HEIGHT} fill="url(#map-bg-radial)" />
              <circle cx={CENTER.x} cy={CENTER.y} r={255} fill="none" stroke="#deebfb" strokeDasharray="3 7" />
              <circle cx={CENTER.x} cy={CENTER.y} r={370} fill="none" stroke="#edf4fd" strokeDasharray="2 9" />

              {mapCategories.map((row) => {
                const node = categoryNodeMap.get(row.category);
                if (!node) return null;
                const start = ellipseBoundaryPoint(CENTER, { x: node.x, y: node.y }, centerEllipse.rx, centerEllipse.ry);
                const end = ellipseBoundaryPoint({ x: node.x, y: node.y }, CENTER, node.rx, node.ry);
                return (
                  <path
                    key={`edge-cat-${row.category}`}
                    d={curvedEdgePath(start, end, 0.09)}
                    fill="none"
                    stroke="url(#edge-cat-grad)"
                    strokeWidth={effectiveCategory === row.category ? 2.8 : 1.9}
                    strokeOpacity={0.9}
                    markerEnd="url(#mind-arrow)"
                    filter="url(#edge-glow)"
                  />
                );
              })}

              {selectedCategoryNode
                ? mapTags.map((row) => {
                    const node = tagNodeMap.get(row.tag);
                    if (!node) return null;
                    const from = { x: selectedCategoryNode.x, y: selectedCategoryNode.y };
                    const start = ellipseBoundaryPoint(from, { x: node.x, y: node.y }, selectedCategoryNode.rx, selectedCategoryNode.ry);
                    const end = ellipseBoundaryPoint({ x: node.x, y: node.y }, from, node.rx, node.ry);
                    return (
                      <path
                        key={`edge-tag-${row.tag}`}
                        d={curvedEdgePath(start, end, 0.1)}
                        fill="none"
                        stroke="url(#edge-tag-grad)"
                        strokeWidth={effectiveTag === row.tag ? 2.5 : 1.8}
                        strokeOpacity={0.92}
                        markerEnd="url(#mind-arrow)"
                        filter="url(#edge-glow)"
                      />
                    );
                  })
                : null}

              {selectedTagNode
                ? mapDocuments.map((row) => {
                    const node = docNodeMap.get(row.id);
                    if (!node) return null;
                    const from = { x: selectedTagNode.x, y: selectedTagNode.y };
                    const start = ellipseBoundaryPoint(from, { x: node.x, y: node.y }, selectedTagNode.rx, selectedTagNode.ry);
                    const end = ellipseBoundaryPoint({ x: node.x, y: node.y }, from, node.rx, node.ry);
                    return (
                      <path
                        key={`edge-doc-${row.id}`}
                        d={curvedEdgePath(start, end, 0.12)}
                        fill="none"
                        stroke="url(#edge-doc-grad)"
                        strokeWidth={1.8}
                        strokeOpacity={0.85}
                        markerEnd="url(#mind-arrow)"
                        filter="url(#edge-glow)"
                      />
                    );
                  })
                : null}

              <MindNode
                id="center"
                label="게시물 마인드맵"
                meta={effectiveTag ? `${effectiveCategory} > ${effectiveTag}` : effectiveCategory || "카테고리 선택"}
                x={CENTER.x}
                y={CENTER.y}
                rx={centerEllipse.rx}
                ry={centerEllipse.ry}
                fill="#ffffff"
                stroke="#5f7fa8"
                strokeWidth={2.4}
                labelFontSize={19}
                metaFontSize={11}
                active
              />

              {mapCategories.map((row) => {
                const node = categoryNodeMap.get(row.category);
                return node ? <MindNode key={node.id} {...node} /> : null;
              })}

              {mapTags.map((row) => {
                const node = tagNodeMap.get(row.tag);
                return node ? <MindNode key={node.id} {...node} /> : null;
              })}

              {mapDocuments.map((row) => {
                const node = docNodeMap.get(row.id);
                return node ? <MindNode key={node.id} {...node} /> : null;
              })}

              <text
                x={CENTER.x}
                y={CENTER.y - 122}
                textAnchor="middle"
                className="fill-slate-500 text-[13px] font-semibold"
                style={{ fontFamily: NODE_FONT_FAMILY }}
              >
                카테고리
              </text>
              {selectedCategoryPoint ? (
                <text
                  x={(CENTER.x + selectedCategoryPoint.x) / 2}
                  y={(CENTER.y + selectedCategoryPoint.y) / 2 - 10}
                  textAnchor="middle"
                  className="fill-slate-500 text-[12px] font-semibold"
                  style={{ fontFamily: NODE_FONT_FAMILY }}
                >
                  태그
                </text>
              ) : null}
              {selectedTagPoint && selectedCategoryPoint ? (
                <text
                  x={(selectedCategoryPoint.x + selectedTagPoint.x) / 2}
                  y={(selectedCategoryPoint.y + selectedTagPoint.y) / 2 - 8}
                  textAnchor="middle"
                  className="fill-slate-500 text-[12px] font-semibold"
                  style={{ fontFamily: NODE_FONT_FAMILY }}
                >
                  문서
                </text>
              ) : null}
            </g>
          </svg>
        </div>

        <div className="mt-3 flex flex-wrap gap-2 text-xs text-slate-600">
          <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1">카테고리 {mapCategories.length}개</span>
          <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1">태그 {mapTags.length}개</span>
          <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1">문서 노드 {mapDocuments.length}개</span>
          <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1">가중치: 카테고리/태그=문서수, 문서=파일수</span>
          {hiddenCategoryCount > 0 ? <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1">숨김 카테고리 {hiddenCategoryCount}개</span> : null}
          {hiddenTagCount > 0 ? <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1">숨김 태그 {hiddenTagCount}개</span> : null}
          {hiddenDocumentCount > 0 ? <span className="rounded-full border border-slate-200 bg-white px-2.5 py-1">숨김 문서 {hiddenDocumentCount}개</span> : null}
        </div>
      </article>

      <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_10px_30px_rgba(15,23,42,0.08)]">
        <p className="mb-2 text-sm font-semibold text-slate-800">빠른 선택</p>
        <div className="space-y-2">
          <div className="flex flex-wrap gap-1.5">
            {data.categories.map((row) => (
              <button
                key={`quick-cat-${row.category}`}
                className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                  effectiveCategory === row.category
                    ? "border-indigo-400 bg-indigo-50 text-indigo-700"
                    : "border-slate-300 bg-white text-slate-700 hover:bg-slate-100"
                }`}
                type="button"
                onClick={() => {
                  setSelectedCategory(row.category);
                  setSelectedTag(null);
                  setPage(1);
                }}
              >
                {row.category}
              </button>
            ))}
          </div>
          <div className="flex flex-wrap gap-1.5">
            {data.tags.map((row) => (
              <button
                key={`quick-tag-${row.tag}`}
                className={`rounded-full border px-2.5 py-1 text-xs font-medium transition ${
                  effectiveTag === row.tag
                    ? "border-cyan-400 bg-cyan-50 text-cyan-700"
                    : "border-slate-300 bg-white text-slate-700 hover:bg-slate-100"
                }`}
                type="button"
                onClick={() => {
                  setSelectedTag(row.tag);
                  setPage(1);
                }}
              >
                {row.tag === UNTAGGED_LABEL ? "태그없음" : row.tag}
              </button>
            ))}
          </div>
        </div>
      </article>

      <article className="rounded-2xl border border-slate-200 bg-white p-4 shadow-[0_10px_30px_rgba(15,23,42,0.08)]">
        <div className="mb-2 flex items-center justify-between">
          <p className="inline-flex items-center gap-1 text-sm font-semibold text-slate-800">
            <FileText className="h-4 w-4 text-indigo-600" />
            문서 목록
          </p>
          <p className="rounded-full border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-600">
            총 {data.total_documents.toLocaleString("ko-KR")}건
          </p>
        </div>

        {data.documents.length === 0 ? <p className="text-sm text-slate-500">선택된 조건의 문서가 없습니다.</p> : null}
        <ul className="space-y-2">
          {data.documents.map((doc) => (
            <li
              key={doc.id}
              className="rounded-xl border border-slate-200 bg-gradient-to-br from-white to-slate-50 p-2.5 text-xs shadow-sm transition hover:border-sky-300 hover:shadow-md"
            >
              <div className="flex items-start justify-between gap-2">
                <div className="min-w-0">
                  <p className="truncate font-semibold text-slate-900">{doc.title}</p>
                  <p className="mt-0.5 text-slate-600">
                    문서일 {formatDate(doc.event_date)} | 파일 {doc.file_count}개 | 수정 {formatDateTime(doc.updated_at)}
                  </p>
                  <p className="mt-0.5 inline-flex items-center gap-1 text-slate-500">
                    <CalendarDays className="h-3 w-3" />
                    카테고리 {doc.category || "미분류"}
                  </p>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {doc.tags.length === 0 ? <span className="rounded-full bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-600">태그없음</span> : null}
                    {doc.tags.map((tag) => (
                      <span key={`${doc.id}-${tag}`} className="rounded-full bg-cyan-100 px-1.5 py-0.5 text-[11px] font-medium text-cyan-800">
                        {tag}
                      </span>
                    ))}
                  </div>
                </div>
                <Link
                  href={`/documents/${doc.id}`}
                  className="inline-flex shrink-0 items-center gap-1 rounded-lg border border-slate-300 bg-white px-2 py-1 text-[11px] font-medium text-slate-700 transition hover:bg-slate-100"
                >
                  상세
                  <ArrowRight className="h-3 w-3" />
                </Link>
              </div>
            </li>
          ))}
        </ul>

        <div className="mt-3 flex items-center justify-end gap-2 text-xs">
          <button
            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2 py-1 hover:bg-slate-100 disabled:opacity-40"
            onClick={() => setPage((prev) => Math.max(1, prev - 1))}
            disabled={page <= 1 || loading}
            type="button"
          >
            <ChevronLeft className="h-3.5 w-3.5" />
            이전
          </button>
          <span className="text-slate-600">
            {page} / {totalPages}
          </span>
          <button
            className="inline-flex items-center gap-1 rounded-lg border border-slate-300 bg-white px-2 py-1 hover:bg-slate-100 disabled:opacity-40"
            onClick={() => setPage((prev) => Math.min(totalPages, prev + 1))}
            disabled={page >= totalPages || loading}
            type="button"
          >
            다음
            <ChevronRight className="h-3.5 w-3.5" />
          </button>
        </div>
      </article>
    </section>
  );
}
