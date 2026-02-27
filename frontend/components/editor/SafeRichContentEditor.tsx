"use client";

import { Component, type ReactNode, useState } from "react";
import { RichContentEditor, type RichContentAttachmentLink } from "@/components/editor/RichContentEditor";
import { RichContentView } from "@/components/editor/RichContentView";

type RichContentEditorProps = {
  value: string;
  onChange: (next: string) => void;
  minHeightClassName?: string;
  attachmentLinks?: RichContentAttachmentLink[];
};

class EditorErrorBoundary extends Component<
  { children: ReactNode; fallback: (errorMessage: string) => ReactNode },
  { hasError: boolean; errorMessage: string }
> {
  constructor(props: { children: ReactNode; fallback: (errorMessage: string) => ReactNode }) {
    super(props);
    this.state = { hasError: false, errorMessage: "" };
  }

  static getDerivedStateFromError(): { hasError: boolean } {
    return { hasError: true };
  }

  componentDidCatch(error: unknown) {
    // Keep page alive and expose runtime editor error in browser console for debugging.
    console.error("RichContentEditor runtime error:", error);
    const message = error instanceof Error ? error.message : String(error);
    this.setState({ errorMessage: message });
  }

  render() {
    if (this.state.hasError) {
      return this.props.fallback(this.state.errorMessage);
    }
    return this.props.children;
  }
}

function FallbackEditor({
  value,
  onChange,
  minHeightClassName,
  onRetry,
  errorMessage,
}: RichContentEditorProps & { onRetry: () => void; errorMessage?: string }) {
  return (
    <div className="rounded border border-amber-300 bg-amber-50 p-2">
      <p className="mb-2 text-xs text-amber-800">리치 편집기를 불러오지 못해 기본 편집기로 전환했습니다.</p>
      {errorMessage ? <p className="mb-2 text-[11px] text-amber-900">원인: {errorMessage}</p> : null}
      <div className="mb-2">
        <button
          type="button"
          className="rounded border border-amber-400 bg-white px-2 py-1 text-xs text-amber-800 hover:bg-amber-100"
          onClick={onRetry}
        >
          리치 편집기 다시 시도
        </button>
      </div>
      <div className="grid grid-cols-2 gap-2">
        <div className="min-w-0 space-y-1">
          <p className="text-[11px] font-semibold text-amber-900">HTML 코드</p>
          <textarea
            className={`w-full rounded border border-amber-300 bg-white px-2 py-2 font-mono text-xs text-stone-900 ${minHeightClassName || "min-h-[240px]"}`}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            placeholder="본문(HTML 포함)을 입력하세요"
          />
        </div>
        <div className="min-w-0 space-y-1">
          <p className="text-[11px] font-semibold text-amber-900">실시간 미리보기</p>
          <div className={`overflow-auto rounded border border-amber-300 bg-white px-2 py-2 ${minHeightClassName || "min-h-[240px]"}`}>
            <RichContentView html={value} />
          </div>
        </div>
      </div>
    </div>
  );
}

export function SafeRichContentEditor(props: RichContentEditorProps) {
  const [resetKey, setResetKey] = useState(0);

  return (
    <EditorErrorBoundary
      key={resetKey}
      fallback={(errorMessage) => (
        <FallbackEditor
          {...props}
          errorMessage={errorMessage}
          onRetry={() => setResetKey((prev) => prev + 1)}
        />
      )}
    >
      <RichContentEditor {...props} />
    </EditorErrorBoundary>
  );
}
