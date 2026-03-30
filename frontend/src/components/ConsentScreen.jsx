import { useState } from 'react'

const CONSENT_PURPOSES = [
  {
    id: 'data_processing',
    title: 'Обработка персональных данных',
    description: 'Обработка ФИО, телефона и данных детей для консультаций через ИИ-ассистента Эврика.',
    required: true,
  },
  {
    id: 'automated_decisions',
    title: 'Автоматизированные решения ИИ',
    description: 'Согласие на принятие решений на основе автоматизированной обработки данных ИИ-ассистентом (ст. 16 ФЗ-152). Вы имеете право на информацию о логике принятия решений и на обжалование.',
    required: true,
  },
  {
    id: 'crm_sync',
    title: 'Передача данных специалистам',
    description: 'Передача контактных данных менеджерам EdPalm для обработки заявок.',
    required: true,
  },
  {
    id: 'ai_memory',
    title: 'Запоминание контекста',
    description: 'Эврика запоминает факты из диалогов для персонализации будущих разговоров.',
    required: false,
  },
  {
    id: 'notifications',
    title: 'Уведомления',
    description: 'Напоминания о незавершённых заявках и информация об акциях.',
    required: false,
  },
]

export function ConsentScreen({ avatarProps, onAccept, loading, isMinor, minorAge }) {
  const [consents, setConsents] = useState(() => {
    const state = {}
    for (const p of CONSENT_PURPOSES) {
      state[p.id] = p.required // Required ON, optional OFF
    }
    return state
  })
  const [guardianConfirmed, setGuardianConfirmed] = useState(false)

  const requiredAccepted = CONSENT_PURPOSES
    .filter(p => p.required)
    .every(p => consents[p.id])

  const minorBlocked = isMinor && !guardianConfirmed

  const toggle = (id) => {
    const purpose = CONSENT_PURPOSES.find(p => p.id === id)
    if (purpose?.required) return // Can't uncheck required
    setConsents(prev => ({ ...prev, [id]: !prev[id] }))
  }

  const handleAccept = () => {
    if (!requiredAccepted) return
    const granted = Object.entries(consents)
      .filter(([, v]) => v)
      .map(([k]) => k)
    onAccept(granted)
  }

  return (
    <div className="w-full h-dvh flex flex-col bg-[var(--bg-primary)]">
      <div className="flex-1 overflow-y-auto flex flex-col items-center px-5 py-8 max-w-lg mx-auto w-full">

        {/* Avatar */}
        <div className="mb-5 animate-[fade-in-up_0.4s_ease-out]">
          <img
            className="w-20 h-20 rounded-full object-cover ring-2 ring-brand/20"
            alt="Эврика"
            {...avatarProps}
          />
        </div>

        {/* Title */}
        <h1 className="text-[20px] font-bold text-[var(--text-primary)] text-center mb-1 animate-[fade-in-up_0.4s_0.1s_ease-out_both]">
          Добро пожаловать!
        </h1>
        <p className="text-[14px] text-[var(--text-secondary)] text-center mb-6 animate-[fade-in-up_0.4s_0.2s_ease-out_both]">
          Прежде чем начать, ознакомьтесь с условиями обработки данных.
        </p>

        {/* Consent items */}
        <div className="w-full rounded-xl bg-[var(--bg-elevated)] border border-[var(--border-subtle)] overflow-hidden mb-6 animate-[fade-in-up_0.4s_0.3s_ease-out_both]">
          {CONSENT_PURPOSES.map((p, i) => (
            <div
              key={p.id}
              className={`flex items-start gap-3 px-4 py-3.5 ${i > 0 ? 'border-t border-[var(--border-subtle)]' : ''}`}
            >
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-1.5">
                  <span className="text-[14px] font-medium text-[var(--text-primary)]">{p.title}</span>
                  {p.required && (
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-brand/15 text-brand font-medium">обязательно</span>
                  )}
                </div>
                <p className="text-[12px] text-[var(--text-secondary)] mt-0.5 leading-relaxed">{p.description}</p>
              </div>
              <label className="relative inline-flex items-center cursor-pointer shrink-0 mt-1">
                <input
                  type="checkbox"
                  checked={consents[p.id]}
                  onChange={() => toggle(p.id)}
                  disabled={p.required}
                  className="sr-only peer"
                />
                <div className={`w-9 h-5 rounded-full peer after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border after:rounded-full after:h-4 after:w-4 after:transition-all peer-checked:after:translate-x-full ${
                  p.required
                    ? 'bg-brand after:border-brand/30 cursor-not-allowed'
                    : 'bg-[var(--bg-secondary)] peer-checked:bg-brand after:border-[var(--border-subtle)] peer-focus:ring-2 peer-focus:ring-brand/30 cursor-pointer'
                }`} />
              </label>
            </div>
          ))}
        </div>

        {/* Minor-specific legal notice + mandatory guardian checkbox (Art. 9 Part 6 ФЗ-152) */}
        {isMinor && (minorAge == null || minorAge < 14) && (
          <div className="w-full rounded-xl bg-amber-500/10 border border-amber-500/20 p-3 mb-4 animate-[fade-in-up_0.4s_0.35s_ease-out_both]">
            <p className="text-[13px] text-amber-600 dark:text-amber-300 leading-relaxed mb-2">
              Для несовершеннолетних младше 14 лет согласие на обработку персональных данных
              даёт законный представитель (ст. 9 ч. 6 ФЗ-152).
            </p>
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={guardianConfirmed}
                onChange={() => setGuardianConfirmed(v => !v)}
                className="mt-0.5 accent-[var(--brand,#6366f1)]"
              />
              <span className="text-[13px] text-amber-700 dark:text-amber-200 font-medium leading-snug">
                Я являюсь законным представителем (родителем/опекуном) несовершеннолетнего
                и даю согласие от его имени
              </span>
            </label>
          </div>
        )}
        {isMinor && minorAge != null && minorAge >= 14 && (
          <div className="w-full rounded-xl bg-amber-500/10 border border-amber-500/20 p-3 mb-4 animate-[fade-in-up_0.4s_0.35s_ease-out_both]">
            <p className="text-[13px] text-amber-600 dark:text-amber-300 leading-relaxed mb-2">
              Для несовершеннолетних от 14 до 18 лет требуется подтверждение одобрения
              законного представителя (ст. 9 ч. 6 ФЗ-152).
            </p>
            <label className="flex items-start gap-2 cursor-pointer">
              <input
                type="checkbox"
                checked={guardianConfirmed}
                onChange={() => setGuardianConfirmed(v => !v)}
                className="mt-0.5 accent-[var(--brand,#6366f1)]"
              />
              <span className="text-[13px] text-amber-700 dark:text-amber-200 font-medium leading-snug">
                Мой родитель/опекун одобряет использование данного сервиса
              </span>
            </label>
          </div>
        )}

        {/* Legal text */}
        <p className="text-[11px] text-[var(--text-tertiary)] text-center mb-5 leading-relaxed px-2 animate-[fade-in-up_0.4s_0.4s_ease-out_both]">
          Нажимая «Принять», вы даёте согласие на обработку персональных данных
          в соответствии с Федеральным законом №152-ФЗ «О персональных данных».
          Оператор: ООО «ЭдПалм».{' '}
          <a href={`${window.location.origin}${window.location.pathname}#/privacy-policy`}
             target="_blank" rel="noopener noreferrer"
             className="text-brand underline hover:no-underline">
            Политика конфиденциальности
          </a>.{' '}
          Вы можете отозвать согласие в любой момент
          через раздел «Профиль» → «Конфиденциальность».
        </p>

        {/* Accept button */}
        <button
          onClick={handleAccept}
          disabled={!requiredAccepted || loading || minorBlocked}
          className={`w-full max-w-xs py-3 rounded-xl text-[15px] font-semibold transition-all animate-[fade-in-up_0.4s_0.5s_ease-out_both] ${
            requiredAccepted && !loading && !minorBlocked
              ? 'bg-brand text-white hover:bg-[var(--color-brand-hover)] active:scale-[0.98]'
              : 'bg-[var(--bg-secondary)] text-[var(--text-tertiary)] cursor-not-allowed'
          }`}
        >
          {loading ? 'Сохраняю...' : 'Принять и начать'}
        </button>
      </div>
    </div>
  )
}
