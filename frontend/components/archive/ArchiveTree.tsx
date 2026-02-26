export function ArchiveTree() {
  return (
    <div className="rounded-lg border border-stone-200 bg-panel p-3 shadow-panel">
      <h3 className="mb-2 text-sm font-semibold">분류 / 연도 / 월</h3>
      <ul className="space-y-1 text-sm text-stone-700">
        <li>회의</li>
        <li>계약</li>
        <li>기타</li>
      </ul>
    </div>
  );
}
