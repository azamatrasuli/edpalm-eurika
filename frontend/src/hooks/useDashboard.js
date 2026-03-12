import { useCallback, useEffect, useState } from 'react'
import { fetchMetrics, fetchConversations, fetchEscalations, fetchUnanswered } from '../api/dashboard'

function formatDate(d) {
  return d.toISOString().slice(0, 10)
}

function defaultDates() {
  const to = new Date()
  const from = new Date()
  from.setDate(from.getDate() - 7)
  return { from: formatDate(from), to: formatDate(to) }
}

export function useDashboard() {
  const defaults = defaultDates()
  const [dateFrom, setDateFrom] = useState(defaults.from)
  const [dateTo, setDateTo] = useState(defaults.to)
  const [channel, setChannel] = useState('')
  const [metrics, setMetrics] = useState(null)
  const [conversations, setConversations] = useState(null)
  const [escalations, setEscalations] = useState(null)
  const [unanswered, setUnanswered] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    setLoading(true)
    setError('')
    try {
      const params = { date_from: dateFrom, date_to: dateTo }
      if (channel) params.channel = channel

      const [m, c, e, u] = await Promise.all([
        fetchMetrics(params),
        fetchConversations(params),
        fetchEscalations(params),
        fetchUnanswered(params),
      ])
      setMetrics(m)
      setConversations(c)
      setEscalations(e)
      setUnanswered(u)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [dateFrom, dateTo, channel])

  useEffect(() => {
    load()
  }, [load])

  function setPreset(days) {
    const to = new Date()
    const from = new Date()
    from.setDate(from.getDate() - days)
    setDateFrom(formatDate(from))
    setDateTo(formatDate(to))
  }

  return {
    dateFrom, setDateFrom,
    dateTo, setDateTo,
    channel, setChannel,
    setPreset,
    metrics, conversations, escalations, unanswered,
    loading, error,
    reload: load,
  }
}
