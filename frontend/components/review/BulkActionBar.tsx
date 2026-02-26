export function BulkActionBar() {
  return (
    <div className="mb-3 rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm">
      <div className="mb-2 font-semibold text-amber-900">검토 큐 일괄 작업</div>
      <div className="flex gap-2">
        <button className="rounded bg-accent px-3 py-1 text-white">일괄 승인</button>
        <button className="rounded border border-stone-300 px-3 py-1">분류 수정</button>
        <button className="rounded border border-stone-300 px-3 py-1">날짜 보정</button>
      </div>
    </div>
  );
}
