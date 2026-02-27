"use client";

import { useEffect, useMemo, useRef } from "react";
import DOMPurify from "dompurify";
import katex from "katex";
import "katex/dist/katex.min.css";

import { normalizeRichContentHtml } from "@/lib/rich-content";

type RichContentViewProps = {
  html: string;
  className?: string;
};

const ALLOWED_TAGS = [
  "a",
  "b",
  "blockquote",
  "br",
  "code",
  "div",
  "em",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "hr",
  "i",
  "img",
  "li",
  "ol",
  "p",
  "pre",
  "span",
  "strong",
  "table",
  "tbody",
  "td",
  "th",
  "thead",
  "tr",
  "u",
  "ul",
];

const ALLOWED_ATTR = [
  "alt",
  "class",
  "colspan",
  "data-display",
  "data-latex",
  "href",
  "rel",
  "rowspan",
  "src",
  "style",
  "target",
  "title",
];

export function RichContentView({ html, className }: RichContentViewProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);
  const safeHtml = useMemo(
    () =>
      DOMPurify.sanitize(normalizeRichContentHtml(html), {
        ALLOWED_TAGS,
        ALLOWED_ATTR,
      }),
    [html],
  );

  useEffect(() => {
    const root = containerRef.current;
    if (!root) return;
    const formulas = root.querySelectorAll<HTMLElement>(".doc-formula[data-latex]");
    formulas.forEach((node) => {
      const latex = node.dataset.latex || node.textContent || "";
      const displayMode = node.dataset.display === "true";
      try {
        katex.render(latex, node, { throwOnError: false, displayMode });
      } catch {
        // Keep plain text if KaTeX fails to render.
      }
    });
  }, [safeHtml]);

  return (
    <div
      ref={containerRef}
      className={`rich-doc-content ${className || ""}`.trim()}
      dangerouslySetInnerHTML={{ __html: safeHtml }}
    />
  );
}

