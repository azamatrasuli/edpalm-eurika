export function UnansweredTable({ data }) {
  const items = data || []

  return (
    <div className="rounded-xl border border-[var(--border-subtle,#e5e7eb)] bg-[var(--bg-primary,#fff)] p-4">
      <h3 className="text-sm font-medium text-[var(--text-primary,#111)] mb-3">Незакрытые вопросы</h3>
      {items.length === 0 ? (
        <p className="text-[13px] text-[var(--text-secondary,#6b7280)]">Все вопросы покрыты базой знаний</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-[var(--border-subtle,#e5e7eb)]">
                <th className="text-left py-2 pr-3 font-medium text-[var(--text-secondary,#6b7280)]">Вопрос</th>
                <th className="text-right py-2 pr-3 font-medium text-[var(--text-secondary,#6b7280)]">Раз</th>
                <th className="text-left py-2 font-medium text-[var(--text-secondary,#6b7280)]">Последний</th>
              </tr>
            </thead>
            <tbody>
              {items.map((q, i) => (
                <tr key={i} className="border-b border-[var(--border-subtle,#e5e7eb)] last:border-0">
                  <td className="py-2 pr-3 text-[var(--text-primary,#111)] max-w-[300px] truncate">{q.query}</td>
                  <td className="py-2 pr-3 text-right font-medium text-[var(--text-primary,#111)]">{q.count}</td>
                  <td className="py-2 text-[var(--text-secondary,#6b7280)]">
                    {q.last_seen ? new Date(q.last_seen).toLocaleDateString('ru-RU') : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
