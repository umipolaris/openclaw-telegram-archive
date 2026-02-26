"use client";

import Link from "next/link";
import { ChevronRight, Menu } from "lucide-react";
import type { Route } from "next";

type PageMenuHeadingProps = {
  title: string;
  href?: string;
};

export function PageMenuHeading({ title, href }: PageMenuHeadingProps) {
  const openMenu = () => {
    window.dispatchEvent(new Event("open-main-menu"));
  };

  const titleNode = href ? (
    <Link className="text-2xl font-bold text-stone-900 hover:text-accent hover:underline" href={href as Route}>
      {title}
    </Link>
  ) : (
    <span className="text-2xl font-bold text-stone-900">{title}</span>
  );

  return (
    <h1 className="inline-flex items-center gap-2 text-2xl font-bold">
      <button
        className="inline-flex items-center gap-1 rounded-md border border-stone-300 bg-white px-2.5 py-1.5 text-xs font-medium text-stone-700 shadow-sm hover:bg-stone-100"
        onClick={openMenu}
        type="button"
        aria-label="메뉴 열기"
      >
        <Menu className="h-4 w-4" />
        메뉴
      </button>
      <ChevronRight className="h-5 w-5 text-stone-500" />
      {titleNode}
    </h1>
  );
}
