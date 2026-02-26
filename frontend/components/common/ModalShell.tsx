"use client";

import { X } from "lucide-react";
import type { ReactNode } from "react";

type ModalShellProps = {
  open: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
  headerRight?: ReactNode;
  maxWidthClassName?: string;
};

export function ModalShell({
  open,
  title,
  onClose,
  children,
  headerRight,
  maxWidthClassName = "max-w-5xl",
}: ModalShellProps) {
  if (!open) return null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-3 sm:p-4" onClick={onClose}>
      <article
        className={`max-h-[92vh] w-full ${maxWidthClassName} overflow-hidden rounded-xl border border-stone-200 bg-panel p-3 shadow-panel`}
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mb-2 flex items-center justify-between border-b border-stone-200 pb-2">
          <h3 className="text-sm font-semibold text-stone-900">{title}</h3>
          <div className="flex items-center gap-2">
            {headerRight}
            <button
              className="inline-flex items-center gap-1 rounded border border-stone-300 px-2 py-1 text-xs hover:bg-stone-50"
              onClick={onClose}
              type="button"
            >
              <X className="h-3.5 w-3.5" />
              닫기
            </button>
          </div>
        </div>
        <div className="max-h-[calc(92vh-88px)] overflow-y-auto pr-1">{children}</div>
      </article>
    </div>
  );
}
