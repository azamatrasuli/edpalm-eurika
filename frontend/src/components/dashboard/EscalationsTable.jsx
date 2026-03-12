export function EscalationsTable({ data }) {
  const items = data?.items || []

  return (
    <div className="rounded-xl border border-[var(--border-subtle,#e5e7eb)] bg-[var(--bg-primary,#fff)] p-4">
      <h3 className="text-sm font-medium text-[var(--text-primary,#111)] mb-3">Эскалации</h3>
      {items.length === 0 ? (
        <p className="text-[13px] text-[var(--text-secondary,#6b7280)]">Нет эскалаций за период</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-[13px]">
            <thead>
              <tr className="border-b border-[var(--border-subtle,#e5e7eb)]">
                <th className="text-left py-2 pr-3 font-medium text-[var(--text-secondary,#6b7280)]">Причина</th>
                <th className="text-left py-2 pr-3 font-medium text-[var(--text-secondary,#6b7280)]">Канал</th>
                <th className="text-left py-2 font-medium text-[var(--text-secondary,#6b7280)]">Дата</th>
              </tr>
            </thead>
            <tbody>
              {items.map((e) => (
                <tr key={e.id} className="border-b border-[var(--border-subtle,#e5e7eb)] last:border-0">
                  <td className="py-2 pr-3 text-[var(--text-primary,#111)]">{e.reason || '—'}</td>
                  <td className="py-2 pr-3 text-[var(--text-secondary,#6b7280)]">{e.channel || '—'}</td>
                  <td className="py-2 text-[var(--text-secondary,#6b7280)]">
                    {e.created_at ? new Date(e.created_at).toLocaleString('ru-RU') : '—'}
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
