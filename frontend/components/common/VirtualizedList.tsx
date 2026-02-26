"use client";

import { CSSProperties, ReactNode, UIEvent, useMemo, useState } from "react";

type VirtualizedListProps<T> = {
  items: T[];
  rowHeight: number;
  height: number;
  overscan?: number;
  className?: string;
  emptyFallback?: ReactNode;
  renderRow: (item: T, index: number, style: CSSProperties) => ReactNode;
};

export function VirtualizedList<T>({
  items,
  rowHeight,
  height,
  overscan = 4,
  className,
  emptyFallback = null,
  renderRow,
}: VirtualizedListProps<T>) {
  const [scrollTop, setScrollTop] = useState(0);

  const totalHeight = items.length * rowHeight;
  const viewportCount = Math.max(1, Math.ceil(height / rowHeight));

  const { startIndex, endIndex } = useMemo(() => {
    const start = Math.max(0, Math.floor(scrollTop / rowHeight) - overscan);
    const end = Math.min(items.length, start + viewportCount + overscan * 2);
    return { startIndex: start, endIndex: end };
  }, [items.length, overscan, rowHeight, scrollTop, viewportCount]);

  const visibleItems = items.slice(startIndex, endIndex);

  const onScroll = (e: UIEvent<HTMLDivElement>) => {
    setScrollTop((e.currentTarget as HTMLDivElement).scrollTop);
  };

  if (items.length === 0) {
    return <>{emptyFallback}</>;
  }

  return (
    <div className={className} style={{ height, overflowY: "auto" }} onScroll={onScroll}>
      <div style={{ position: "relative", height: totalHeight }}>
        {visibleItems.map((item, offset) => {
          const index = startIndex + offset;
          const style: CSSProperties = {
            position: "absolute",
            top: index * rowHeight,
            left: 0,
            right: 0,
            height: rowHeight,
          };
          return renderRow(item, index, style);
        })}
      </div>
    </div>
  );
}
