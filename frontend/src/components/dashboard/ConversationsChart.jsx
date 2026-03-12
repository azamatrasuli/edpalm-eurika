import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid } from 'recharts'

export function ConversationsChart({ data }) {
  if (!data || data.length === 0) {
    return <p className="text-[13px] text-[var(--text-secondary,#6b7280)] py-4">Нет данных за выбранный период</p>
  }

  const formatted = data.map((d) => ({
    ...d,
    label: d.date.slice(5), // MM-DD
  }))

  return (
    <div className="rounded-xl border border-[var(--border-subtle,#e5e7eb)] bg-[var(--bg-primary,#fff)] p-4">
      <h3 className="text-sm font-medium text-[var(--text-primary,#111)] mb-3">Диалоги по дням</h3>
      <ResponsiveContainer width="100%" height={220}>
        <BarChart data={formatted}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle, #e5e7eb)" />
          <XAxis dataKey="label" tick={{ fontSize: 12, fill: 'var(--text-secondary, #6b7280)' }} />
          <YAxis tick={{ fontSize: 12, fill: 'var(--text-secondary, #6b7280)' }} allowDecimals={false} />
          <Tooltip
            contentStyle={{ fontSize: 13, borderRadius: 8, border: '1px solid var(--border-subtle, #e5e7eb)' }}
            formatter={(val) => [val, 'Диалоги']}
          />
          <Bar dataKey="conversations" fill="var(--btn-primary, #6366f1)" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  )
}
