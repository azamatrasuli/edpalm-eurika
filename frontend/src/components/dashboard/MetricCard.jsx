export function MetricCard({ label, value, suffix = '' }) {
  return (
    <div className="rounded-xl border border-[var(--border-subtle,#e5e7eb)] bg-[var(--bg-primary,#fff)] p-4 min-w-[140px]">
      <p className="text-[13px] text-[var(--text-secondary,#6b7280)] mb-1">{label}</p>
      <p className="text-2xl font-bold text-[var(--text-primary,#111)]">
        {value}{suffix && <span className="text-sm font-normal ml-0.5">{suffix}</span>}
      </p>
    </div>
  )
}
