"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { EditorContent, useEditor } from "@tiptap/react";
import StarterKit from "@tiptap/starter-kit";
import { TextStyle } from "@tiptap/extension-text-style";
import Color from "@tiptap/extension-color";
import Highlight from "@tiptap/extension-highlight";
import Image from "@tiptap/extension-image";
import Link from "@tiptap/extension-link";
import Underline from "@tiptap/extension-underline";
import { Code2, Eraser, ImagePlus, Link2, Sigma } from "lucide-react";

import { escapeHtml, normalizeRichContentHtml } from "@/lib/rich-content";
import { RichContentView } from "@/components/editor/RichContentView";

type RichContentEditorProps = {
  value: string;
  onChange: (next: string) => void;
  minHeightClassName?: string;
  attachmentLinks?: RichContentAttachmentLink[];
};

type EditorViewMode = "visual" | "html";

export type RichContentAttachmentLink = {
  label: string;
  href: string;
};

function buttonClass(active = false): string {
  if (active) {
    return "rounded border border-accent bg-accent px-2 py-1 text-[11px] font-medium text-white";
  }
  return "rounded border border-stone-300 bg-white px-2 py-1 text-[11px] text-stone-700 hover:bg-stone-50";
}

export function RichContentEditor({
  value,
  onChange,
  minHeightClassName = "min-h-[240px]",
  attachmentLinks = [],
}: RichContentEditorProps) {
  const fileInputRef = useRef<HTMLInputElement | null>(null);
  const normalizedInitial = useMemo(() => normalizeRichContentHtml(value), [value]);
  const normalizedAttachmentLinks = useMemo(
    () =>
      attachmentLinks
        .map((item) => ({
          label: item.label?.trim() || item.href?.trim() || "첨부파일",
          href: item.href?.trim() || "",
        }))
        .filter((item) => item.href.length > 0),
    [attachmentLinks],
  );
  const [viewMode, setViewMode] = useState<EditorViewMode>("visual");
  const [htmlSource, setHtmlSource] = useState<string>(normalizedInitial);
  const [selectedAttachmentHref, setSelectedAttachmentHref] = useState("");
  const editor = useEditor({
    immediatelyRender: false,
    extensions: [
      StarterKit,
      Underline,
      TextStyle,
      Color,
      Highlight.configure({ multicolor: true }),
      Link.configure({ openOnClick: false }),
      Image.configure({ allowBase64: true }),
    ],
    content: normalizedInitial,
    editorProps: {
      attributes: {
        class:
          `rich-editor-content w-full rounded border border-stone-300 bg-white px-3 py-3 text-sm text-stone-900 focus:outline-none ${minHeightClassName}`,
      },
    },
    onUpdate: ({ editor: ed }) => {
      const html = ed.getHTML();
      setHtmlSource(html);
      onChange(html);
    },
  });

  useEffect(() => {
    if (!editor) return;
    const normalized = normalizeRichContentHtml(value);
    if (viewMode === "visual") {
      if (editor.getHTML() !== normalized) {
        editor.commands.setContent(normalized, { emitUpdate: false });
      }
      setHtmlSource(normalized);
    }
  }, [editor, value, viewMode]);

  useEffect(() => {
    if (normalizedAttachmentLinks.length === 0) {
      if (selectedAttachmentHref) setSelectedAttachmentHref("");
      return;
    }
    if (!normalizedAttachmentLinks.some((item) => item.href === selectedAttachmentHref)) {
      setSelectedAttachmentHref(normalizedAttachmentLinks[0].href);
    }
  }, [normalizedAttachmentLinks, selectedAttachmentHref]);

  const insertImageUrl = () => {
    if (!editor) return;
    const url = window.prompt("이미지 URL을 입력하세요");
    if (!url) return;
    editor.chain().focus().setImage({ src: url, alt: "embedded-image" }).run();
  };

  const insertImageFile = (file: File) => {
    if (!editor) return;
    if (!file.type.startsWith("image/")) return;
    const reader = new FileReader();
    reader.onload = () => {
      const result = typeof reader.result === "string" ? reader.result : "";
      if (!result) return;
      editor.chain().focus().setImage({ src: result, alt: file.name }).run();
    };
    reader.readAsDataURL(file);
  };

  const insertLink = () => {
    if (!editor) return;
    const url = window.prompt("링크 URL을 입력하세요");
    if (!url) return;
    editor.chain().focus().setLink({ href: url, target: "_blank", rel: "noopener noreferrer" }).run();
  };

  const insertAttachmentLink = () => {
    if (!editor || !selectedAttachmentHref) return;
    const selected =
      normalizedAttachmentLinks.find((item) => item.href === selectedAttachmentHref) || normalizedAttachmentLinks[0];
    if (!selected) return;
    const href = escapeHtml(selected.href);
    const label = escapeHtml(selected.label || selected.href);
    editor.chain().focus().insertContent(`<a href="${href}" target="_blank" rel="noopener noreferrer">${label}</a>`).run();
  };

  const insertFormula = (display: boolean) => {
    if (!editor) return;
    const latex = window.prompt("LaTeX 수식을 입력하세요 (예: E=mc^2)");
    if (!latex) return;
    const escaped = escapeHtml(latex);
    const displayAttr = display ? "true" : "false";
    editor
      .chain()
      .focus()
      .insertContent(
        display
          ? `<div><span class="doc-formula" data-latex="${escaped}" data-display="${displayAttr}">${escaped}</span></div>`
          : `<span class="doc-formula" data-latex="${escaped}" data-display="${displayAttr}">${escaped}</span>`,
      )
      .run();
  };

  const switchToHtmlMode = () => {
    if (editor) {
      setHtmlSource(editor.getHTML());
    }
    setViewMode("html");
  };

  const applyHtmlSource = () => {
    if (!editor) return;
    const normalized = normalizeRichContentHtml(htmlSource);
    editor.commands.setContent(normalized, { emitUpdate: false });
    onChange(normalized);
    setViewMode("visual");
  };

  if (!editor) {
    return <p className="text-xs text-stone-500">에디터 로딩 중...</p>;
  }

  return (
    <div className="rounded border border-stone-300 bg-stone-50">
      <div className="flex flex-wrap items-center gap-1 border-b border-stone-300 bg-white px-2 py-2">
        <input
          type="color"
          className="h-7 w-7 cursor-pointer rounded border border-stone-300 bg-white p-1"
          onChange={(e) => editor.chain().focus().setColor(e.target.value).run()}
          title="글자색"
        />
        <button type="button" className={buttonClass(editor.isActive("bold"))} onClick={() => editor.chain().focus().toggleBold().run()}>
          B
        </button>
        <button type="button" className={buttonClass(editor.isActive("italic"))} onClick={() => editor.chain().focus().toggleItalic().run()}>
          I
        </button>
        <button type="button" className={buttonClass(editor.isActive("underline"))} onClick={() => editor.chain().focus().toggleUnderline().run()}>
          U
        </button>
        <button
          type="button"
          className={buttonClass(editor.isActive("highlight"))}
          onClick={() => editor.chain().focus().toggleHighlight({ color: "#fde68a" }).run()}
        >
          형광
        </button>
        <button type="button" className={buttonClass(editor.isActive("heading", { level: 1 }))} onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}>
          H1
        </button>
        <button type="button" className={buttonClass(editor.isActive("heading", { level: 2 }))} onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}>
          H2
        </button>
        <button type="button" className={buttonClass(editor.isActive("bulletList"))} onClick={() => editor.chain().focus().toggleBulletList().run()}>
          목록
        </button>
        <button type="button" className={buttonClass(editor.isActive("orderedList"))} onClick={() => editor.chain().focus().toggleOrderedList().run()}>
          번호
        </button>
        <button type="button" className={buttonClass(editor.isActive("blockquote"))} onClick={() => editor.chain().focus().toggleBlockquote().run()}>
          인용
        </button>
        <button type="button" className={buttonClass(editor.isActive("codeBlock"))} onClick={() => editor.chain().focus().toggleCodeBlock().run()}>
          코드
        </button>
        <button type="button" className={buttonClass()} onClick={insertLink} title="링크">
          <Link2 className="h-3.5 w-3.5" />
        </button>
        {normalizedAttachmentLinks.length > 0 ? (
          <>
            <select
              className="h-7 max-w-[14rem] rounded border border-stone-300 bg-white px-2 text-[11px] text-stone-700"
              value={selectedAttachmentHref}
              onChange={(e) => setSelectedAttachmentHref(e.target.value)}
              title="첨부파일 선택"
            >
              {normalizedAttachmentLinks.map((item) => (
                <option key={`${item.href}-${item.label}`} value={item.href}>
                  {item.label}
                </option>
              ))}
            </select>
            <button type="button" className={buttonClass()} onClick={insertAttachmentLink} title="첨부파일 링크 삽입">
              첨부링크
            </button>
          </>
        ) : null}
        <button type="button" className={buttonClass()} onClick={insertImageUrl} title="이미지 URL">
          <ImagePlus className="h-3.5 w-3.5" />
          URL
        </button>
        <button
          type="button"
          className={buttonClass()}
          onClick={() => fileInputRef.current?.click()}
          title="이미지 파일 삽입"
        >
          <ImagePlus className="h-3.5 w-3.5" />
          파일
        </button>
        <button type="button" className={buttonClass()} onClick={() => insertFormula(false)} title="인라인 수식">
          <Sigma className="h-3.5 w-3.5" />
          수식
        </button>
        <button type="button" className={buttonClass()} onClick={() => insertFormula(true)} title="블록 수식">
          <Sigma className="h-3.5 w-3.5" />
          수식블록
        </button>
        <button
          type="button"
          className={buttonClass()}
          onClick={() => editor.chain().focus().unsetAllMarks().clearNodes().run()}
          title="서식 제거"
        >
          <Eraser className="h-3.5 w-3.5" />
        </button>
        {viewMode === "visual" ? (
          <button type="button" className={buttonClass()} onClick={switchToHtmlMode} title="HTML 소스 보기">
            <Code2 className="h-3.5 w-3.5" />
            HTML
          </button>
        ) : (
          <button type="button" className={buttonClass(true)} onClick={applyHtmlSource} title="HTML 적용 후 시각 모드">
            <Code2 className="h-3.5 w-3.5" />
            시각모드
          </button>
        )}
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) insertImageFile(file);
            e.currentTarget.value = "";
          }}
        />
      </div>
      {viewMode === "visual" ? (
        <div className="grid grid-cols-2 gap-2 rounded-b border border-t-0 border-stone-300 bg-stone-50 p-2">
          <div className="min-w-0 space-y-1">
            <p className="text-[11px] font-semibold text-stone-700">시각 편집</p>
            <EditorContent editor={editor} />
          </div>
          <div className="min-w-0 space-y-1">
            <p className="text-[11px] font-semibold text-stone-700">실시간 미리보기</p>
            <div className={`overflow-auto rounded border border-stone-300 bg-white px-3 py-3 ${minHeightClassName}`}>
              <RichContentView html={htmlSource} />
            </div>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-2 rounded-b border border-t-0 border-stone-300 bg-stone-50 p-2">
          <div className="min-w-0 space-y-1">
            <p className="text-[11px] font-semibold text-stone-700">HTML 코드</p>
            <textarea
              className={`w-full rounded border border-stone-300 bg-white px-3 py-3 font-mono text-xs text-stone-900 focus:outline-none ${minHeightClassName}`}
              value={htmlSource}
              onChange={(e) => {
                const next = e.target.value;
                setHtmlSource(next);
                onChange(next);
              }}
              spellCheck={false}
            />
          </div>
          <div className="min-w-0 space-y-1">
            <p className="text-[11px] font-semibold text-stone-700">실시간 미리보기</p>
            <div className={`overflow-auto rounded border border-stone-300 bg-white px-3 py-3 ${minHeightClassName}`}>
              <RichContentView html={htmlSource} />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
