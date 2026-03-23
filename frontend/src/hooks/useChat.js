import { useCallback, useEffect, useRef, useState } from 'react'
import { fetchMessages, pollMessages, startConversation, streamChat } from '../api/client'
import { isManagerMode } from '../lib/authContext'

function getStorageKey(agentRole) {
  return `eurika_conversation_id_${agentRole}`
}

export function useChat(auth, agentRole = 'sales', onboardingComplete = true, { initialConvId = null } = {}) {
  const [messages, setMessages] = useState([])
  const [conversationId, setConversationId] = useState('')
  const [typing, setTyping] = useState(false)
  const [toolStatus, setToolStatus] = useState('')
  const [error, setError] = useState('')
  const [started, setStarted] = useState(false)
  const [loading, setLoading] = useState(false)
  const [escalated, setEscalated] = useState(false)
  const [escalationReason, setEscalationReason] = useState('')
  const [suggestions, setSuggestions] = useState([])
  const abortRef = useRef(null)
  const initRef = useRef(false)
  const conversationIdRef = useRef(conversationId)
  const titleCallbackRef = useRef(null)
  const bumpCallbackRef = useRef(null)

  // --- Load a conversation (new or existing) ---
  const loadConversation = useCallback(async (convId = null, forceNew = false) => {
    if (!auth) return null

    // Abort any in-flight stream
    if (abortRef.current) {
      abortRef.current.abort()
      abortRef.current = null
    }

    setLoading(true)
    setTyping(false)
    setError('')
    // Only reset escalation on forced new conversation
    if (forceNew) {
      setEscalated(false)
      setEscalationReason('')
    }

    try {
      const data = await startConversation(auth, convId, agentRole, forceNew)
      setConversationId(data.conversation_id)
      conversationIdRef.current = data.conversation_id
      const storageKey = getStorageKey(agentRole)
      try { sessionStorage.setItem(storageKey, data.conversation_id) } catch { /* quota */ }

      // Restore escalation state from backend
      if (data.status === 'escalated') {
        setEscalated(true)
        setEscalationReason(data.escalated_reason || '')
      } else {
        setEscalated(false)
        setEscalationReason('')
      }

      // Try to restore message history for existing conversations
      if (convId && data.conversation_id === convId && !forceNew) {
        try {
          const historyData = await fetchMessages(convId, auth)
          if (historyData.messages && historyData.messages.length > 0) {
            setMessages(
              historyData.messages
                .filter((m) => m.role !== 'system')
                .map((m) => ({
                  id: crypto.randomUUID(),
                  role: m.role,
                  content: m.content,
                  fromHistory: true,
                  type: m.metadata?.source === 'manager' ? 'manager' : undefined,
                })),
            )
            // Also check escalation from messages endpoint
            if (historyData.status === 'escalated') {
              setEscalated(true)
              setEscalationReason(historyData.escalated_reason || '')
            }
            setStarted(true)
            setLoading(false)
            return data
          }
        } catch {
          // History fetch failed — fall through to new greeting
        }
      }

      // Build greeting
      const greeting = data?.greeting || 'Привет! Я Эврика из EdPalm. Чем могу помочь?'
      const initMessages = [
        { id: crypto.randomUUID(), role: 'assistant', content: greeting },
      ]

      setMessages(initMessages)
      setStarted(true)
      setLoading(false)
      return data
    } catch (e) {
      let errMsg
      if (e instanceof TypeError && e.message.includes('fetch')) {
        errMsg = 'Нет подключения к серверу. Проверьте интернет и попробуйте снова.'
      } else if (e.code === 'auth_expired' || e.code === 'auth_invalid') {
        errMsg = 'Сессия истекла. Обновите страницу.'
      } else {
        errMsg = e.message || 'Не удалось загрузить чат. Попробуйте обновить страницу.'
      }
      setError(errMsg)
      setLoading(false)
      return null
    }
  }, [auth, agentRole])

  // --- Initial load on mount ---
  useEffect(() => {
    if (!auth || initRef.current || !onboardingComplete) return
    initRef.current = true

    // Priority: URL param > sessionStorage
    const convId = initialConvId || sessionStorage.getItem(getStorageKey(agentRole))
    loadConversation(convId)
  }, [auth, agentRole, onboardingComplete, loadConversation])

  // Keep conversationIdRef in sync
  useEffect(() => {
    conversationIdRef.current = conversationId
  }, [conversationId])

  // Cleanup abort controller on unmount
  useEffect(() => {
    return () => {
      if (abortRef.current) {
        abortRef.current.abort()
        abortRef.current = null
      }
    }
  }, [])

  // --- SSE Live Channel: real-time message delivery ---
  const seenMsgIdsRef = useRef(new Set())

  useEffect(() => {
    if (!conversationId) return

    // Build auth query params for SSE endpoint
    const params = new URLSearchParams()
    if (auth.manager_key) params.set('key', auth.manager_key)
    if (auth.guest_id) params.set('guest_id', auth.guest_id)

    const API_BASE = import.meta.env.VITE_API_BASE_URL
      || (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
        ? 'http://127.0.0.1:8009'
        : 'https://edpalm-eurika-ws1a.onrender.com')

    const url = `${API_BASE}/api/v1/chat/listen/${conversationId}?${params.toString()}`
    const evtSource = new EventSource(url)

    evtSource.addEventListener('new_message', (e) => {
      try {
        const msg = JSON.parse(e.data)
        // Dedup: skip messages we already have
        if (seenMsgIdsRef.current.has(msg.id)) return
        seenMsgIdsRef.current.add(msg.id)

        const isManager = msg.metadata?.source === 'manager'
        const isSystem = msg.metadata?.source === 'system'

        setMessages((prev) => {
          // Also check if content already exists (sent by us)
          if (prev.some((m) => m.dbId === msg.id)) return prev
          // Skip if this is our own message just sent (content match)
          const managerMode = isManagerMode()
          if (managerMode && isManager && prev.some((m) => m.content === msg.content && m.type === 'manager')) return prev
          if (!managerMode && msg.role === 'user' && prev.some((m) => m.content === msg.content && m.role === 'user')) return prev

          return [
            ...prev,
            {
              id: crypto.randomUUID(),
              dbId: msg.id,
              role: msg.role,
              content: msg.content,
              type: isManager ? 'manager' : isSystem ? 'system' : undefined,
              senderName: msg.metadata?.sender_name || (isManager ? 'Менеджер' : undefined),
              fromHistory: true,
            },
          ]
        })
      } catch {
        // ignore parse errors
      }
    })

    evtSource.addEventListener('status', (e) => {
      try {
        const data = JSON.parse(e.data)
        if (data.manager_active !== undefined) {
          // Could update UI state here
        }
      } catch { /* ignore */ }
    })

    evtSource.onerror = () => {
      // SSE reconnects automatically
    }

    return () => evtSource.close()
  }, [conversationId, auth])

  // --- Switch to an existing conversation ---
  const switchConversation = useCallback(async (convId) => {
    if (convId === conversationIdRef.current) return
    await loadConversation(convId)
  }, [loadConversation])

  // --- Start a completely new conversation ---
  const startNewChat = useCallback(async () => {
    const data = await loadConversation(null, true)
    return data
  }, [loadConversation])

  const sendMessage = useCallback(async (text) => {
    const currentConvId = conversationIdRef.current
    if (!text.trim() || !auth || !currentConvId || typing || escalated) return

    setSuggestions([])

    // Manager mode: show as manager bubble (blue, left), not as user (green, right)
    const managerMode = isManagerMode()
    const assistantId = crypto.randomUUID()

    if (managerMode) {
      // Manager message: show immediately as manager type, no empty assistant placeholder
      const mgrMsg = {
        id: crypto.randomUUID(),
        role: 'assistant',
        content: text,
        type: 'manager',
        senderName: 'Менеджер',
      }
      setMessages((prev) => [...prev, mgrMsg])
    } else {
      const userMsg = { id: crypto.randomUUID(), role: 'user', content: text }
      setMessages((prev) => [...prev, userMsg, { id: assistantId, role: 'assistant', content: '' }])
    }
    setTyping(!managerMode) // manager doesn't wait for LLM
    setToolStatus('')
    setError('')

    const controller = new AbortController()
    abortRef.current = controller

    const storageKey = getStorageKey(agentRole)

    // Show "warming up" hint if server is slow (Render cold start)
    let gotFirstToken = false
    const warmingTimer = setTimeout(() => {
      if (!gotFirstToken) setToolStatus('Сервер загружается...')
    }, 8000)

    try {
      await streamChat({
        auth,
        conversationId: currentConvId,
        message: text,
        agentRole,
        signal: controller.signal,
        onEvent: (event, payload) => {
          if (!gotFirstToken && (event === 'token' || event === 'meta' || event === 'tool_call')) {
            gotFirstToken = true
            clearTimeout(warmingTimer)
          }

          if (event === 'meta' && payload.conversation_id && payload.conversation_id !== conversationIdRef.current) {
            setConversationId(payload.conversation_id)
            conversationIdRef.current = payload.conversation_id
            try { sessionStorage.setItem(storageKey, payload.conversation_id) } catch { /* quota */ }
          }

          if (event === 'tool_call') {
            setToolStatus(payload.label || 'Обрабатываю...')
          }

          if (event === 'token') {
            setToolStatus('')
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, content: `${m.content}${payload.text || ''}` } : m,
              ),
            )
          }

          if (event === 'payment_card') {
            setMessages((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: '',
                type: 'payment',
                paymentData: payload,
              },
            ])
          }

          if (event === 'escalation') {
            setEscalated(true)
            setEscalationReason(payload.reason || '')
          }

          if (event === 'manager_message') {
            setMessages((prev) => [
              ...prev,
              {
                id: crypto.randomUUID(),
                role: 'assistant',
                content: payload.text,
                type: 'manager',
                senderName: payload.sender,
              },
            ])
          }

          // Title update from backend — push to sidebar
          if (event === 'title' && payload.title) {
            if (titleCallbackRef.current) {
              titleCallbackRef.current(payload.conversation_id, payload.title)
            }
          }

          if (event === 'suggestions' && payload.chips) {
            setSuggestions(payload.chips)
          }

          // Manager is active — client message went to manager, not AI
          if (event === 'status' && payload.manager_active) {
            setTyping(false)
            setToolStatus('')
            // Remove empty assistant placeholder
            setMessages((prev) => prev.filter((m) => m.id !== assistantId || m.content))
          }

          if (event === 'done') {
            setTyping(false)
            setToolStatus('')
            // Remove empty assistant placeholder (manager mode or no-response)
            setMessages((prev) => prev.filter((m) => m.id !== assistantId || m.content))
            // Update sidebar metadata reactively
            if (bumpCallbackRef.current) {
              bumpCallbackRef.current(conversationIdRef.current, text)
            }
          }
        },
      })
    } catch (e) {
      if (e.name === 'AbortError') return
      setTyping(false)
      // Mark partial response if tokens were received before error
      setMessages((prev) =>
        prev.map((m) =>
          m.id === assistantId && m.content
            ? { ...m, content: `${m.content}\n\n_(ответ неполный)_` }
            : m,
        ),
      )
      let errMsg
      if (e.message === 'SSE_TIMEOUT') {
        errMsg = 'Сервер не ответил вовремя. Попробуйте ещё раз.'
      } else if (e.code === 'offline' || (e instanceof TypeError && e.message.includes('fetch'))) {
        errMsg = 'Нет подключения к интернету. Проверьте соединение и попробуйте снова.'
      } else if (e.code === 'rate_limit') {
        errMsg = 'Слишком много сообщений. Подождите минуту.'
      } else if (e.code === 'auth_expired' || e.code === 'auth_invalid') {
        errMsg = 'Сессия истекла. Обновите страницу.'
      } else if (e.code === 'message_too_long') {
        errMsg = 'Сообщение слишком длинное (максимум 4000 символов).'
      } else if (e.code === 'stt_unavailable') {
        errMsg = 'Распознавание речи временно недоступно. Напишите текстом.'
      } else if (e.code === 'internal_error') {
        errMsg = 'Ошибка сервера. Попробуйте через пару минут.'
      } else {
        errMsg = e.message || 'Что-то пошло не так. Попробуйте ещё раз.'
      }
      setError(errMsg)
    } finally {
      clearTimeout(warmingTimer)
      abortRef.current = null
    }
  }, [auth, agentRole, typing, escalated])

  const clearSuggestions = useCallback(() => setSuggestions([]), [])

  // Register callbacks (called from ChatPage)
  const onTitleUpdate = useCallback((cb) => {
    titleCallbackRef.current = cb
  }, [])

  const onBumpConversation = useCallback((cb) => {
    bumpCallbackRef.current = cb
  }, [])

  const addSystemMessage = useCallback((text) => {
    setMessages((prev) => [
      ...prev,
      { id: crypto.randomUUID(), role: 'assistant', content: text, type: 'system' },
    ])
  }, [])

  return {
    messages,
    conversationId,
    sendMessage,
    typing,
    toolStatus,
    error,
    started,
    loading,
    escalated,
    escalationReason,
    switchConversation,
    startNewChat,
    suggestions,
    clearSuggestions,
    onTitleUpdate,
    onBumpConversation,
    addSystemMessage,
  }
}
