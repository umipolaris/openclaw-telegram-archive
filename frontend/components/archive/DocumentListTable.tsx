export function DocumentListTable() {
  return (
    <div className="rounded-lg border border-stone-200 bg-panel p-3 shadow-panel">
      <h3 className="mb-2 text-sm font-semibold">문서 목록</h3>
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-stone-200 text-stone-500">
            <th className="py-2">제목</th>
            <th className="py-2">날짜</th>
            <th className="py-2">태그</th>
            <th className="py-2">검토</th>
          </tr>
        </thead>
        <tbody>
          <tr className="border-b border-stone-100">
            <td className="py-2">주간 운영회의</td>
            <td className="py-2">2026-02-24</td>
            <td className="py-2">alpha, beta</td>
            <td className="py-2">정상</td>
          </tr>
        </tbody>
      </table>
    </div>
  );
}
