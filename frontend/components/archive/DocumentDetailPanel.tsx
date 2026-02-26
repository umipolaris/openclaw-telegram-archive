export function DocumentDetailPanel() {
  return (
    <div className="rounded-lg border border-stone-200 bg-panel p-3 shadow-panel">
      <h3 className="mb-2 text-sm font-semibold">문서 상세</h3>
      <div className="space-y-2 text-sm text-stone-700">
        <p>원본 캡션</p>
        <p>파일 목록</p>
        <p>버전 히스토리</p>
      </div>
    </div>
  );
}
