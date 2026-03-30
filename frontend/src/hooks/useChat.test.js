import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import { useChat } from './useChat.js'

// ---------------------------------------------------------------------------
// Controllable streamChat mock
// ---------------------------------------------------------------------------
let streamResolve = null
let streamReject = null
let streamOnEvent = null
let streamSignal = null

const mockStreamChat = vi.fn(({ onEvent, signal }) => {
  streamOnEvent = onEvent
  streamSignal = signal
  return new Promise((resolve, reject) => {
    streamResolve = resolve
    streamReject = reject
    if (signal?.aborted) {
      reject(new DOMException('aborted', 'AbortError'))
      return
    }
    signal?.addEventListener('abort', () => {
      reject(new DOMException('aborted', 'AbortError'))
    })
  })
})

const mockStartConversation = vi.fn()
const mockFetchMessages = vi.fn()

vi.mock('../api/client', () => ({
  streamChat: (...a) => mockStreamChat(...a),
  startConversation: (...a) => mockStartConversation(...a),
  fetchMessages: (...a) => mockFetchMessages(...a),
  pollMessages: vi.fn().mockResolvedValue({ messages: [] }),
}))

vi.mock('../lib/authContext', () => ({
  isManagerMode: () => false,
}))

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------
if (!globalThis.EventSource) {
  globalThis.EventSource = class {
    constructor() { this.close = vi.fn() }
    addEventListener() {}
    set onopen(_) {}
    set onerror(_) {}
  }
}

const AUTH = { portal_token: 'test-jwt' }
const CONV_ID = 'conv-123'
const flush = (ms = 30) => new Promise((r) => setTimeout(r, ms))

function resetStream() {
  streamResolve = null
  streamReject = null
  streamOnEvent = null
  streamSignal = null
  mockStreamChat.mockClear()
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

async function mountChat(convId = CONV_ID) {
  mockStartConversation.mockResolvedValue({
    conversation_id: convId,
    greeting: 'Привет!',
  })
  mockFetchMessages.mockResolvedValue({
    messages: [{ role: 'assistant', content: 'Привет!', metadata: {} }],
  })
  try { sessionStorage.setItem('eurika_conversation_id_sales', convId) } catch {}

  const hook = renderHook(() => useChat(AUTH, 'sales', true))
  // Flush async loadConversation
  await act(async () => { await flush() })
  return hook
}

async function sendMsg(result, text = 'тест') {
  resetStream()
  await act(async () => {
    result.current.sendMessage(text)
    await flush()
  })
}

async function finishStream() {
  await act(async () => {
    streamOnEvent?.('done', {})
    streamResolve?.()
    await flush()
  })
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------
describe('useChat — SSE stream survival on unmount', () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    vi.clearAllMocks()
    resetStream()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  // =========================================================================
  // 1. Stream is NOT aborted on component unmount
  // =========================================================================
  it('should NOT abort active stream when component unmounts', async () => {
    const { result, unmount } = await mountChat()
    expect(result.current.started).toBe(true)

    await sendMsg(result)
    expect(streamSignal).not.toBeNull()
    expect(streamSignal.aborted).toBe(false)

    // User navigates away
    unmount()

    // KEY: signal must NOT be aborted
    expect(streamSignal.aborted).toBe(false)

    await finishStream()
  })

  // =========================================================================
  // 2. Full history loaded on remount after bg stream completes
  // =========================================================================
  it('should load full history from backend after unmount+remount', async () => {
    const { result, unmount } = await mountChat()
    await sendMsg(result)

    unmount()
    await finishStream() // backend saves full response

    // Backend returns full history on re-mount
    mockFetchMessages.mockResolvedValueOnce({
      messages: [
        { role: 'assistant', content: 'Привет!', metadata: {} },
        { role: 'user', content: 'тест', metadata: {} },
        { role: 'assistant', content: 'Полный ответ из БД', metadata: {} },
      ],
    })

    const { result: r2 } = await mountChat()
    const assistantMsgs = r2.current.messages.filter((m) => m.role === 'assistant')
    const last = assistantMsgs[assistantMsgs.length - 1]
    expect(last.content).toBe('Полный ответ из БД')
  })

  // =========================================================================
  // 3. Conversation switch still aborts
  // =========================================================================
  it('should abort stream when switching to a DIFFERENT conversation', async () => {
    const { result } = await mountChat()
    await sendMsg(result)

    const sig = streamSignal
    expect(sig.aborted).toBe(false)

    mockStartConversation.mockResolvedValueOnce({
      conversation_id: 'conv-456',
      greeting: 'Другой чат',
    })
    await act(async () => {
      result.current.switchConversation('conv-456')
      await flush()
    })

    expect(sig.aborted).toBe(true)
  })

  // =========================================================================
  // 4. startNewChat aborts
  // =========================================================================
  it('should abort stream when starting a new chat', async () => {
    const { result } = await mountChat()
    await sendMsg(result)

    const sig = streamSignal

    mockStartConversation.mockResolvedValueOnce({
      conversation_id: 'conv-new',
      greeting: 'Новый диалог',
    })
    await act(async () => {
      result.current.startNewChat()
      await flush()
    })

    expect(sig.aborted).toBe(true)
  })

  // =========================================================================
  // 5. Background stream is awaited on remount
  // =========================================================================
  it('should await background stream before loading messages on remount', async () => {
    const { result, unmount } = await mountChat()
    await sendMsg(result)

    // Unmount while stream is running
    unmount()

    // Track fetch calls for the second mount
    let fetchCalledBeforeStreamEnd = false
    const origFetchMessages = mockFetchMessages.getMockImplementation()

    // New mock: record timing relative to stream completion
    let streamFinished = false
    mockFetchMessages.mockImplementation(async (...args) => {
      if (!streamFinished) fetchCalledBeforeStreamEnd = true
      return {
        messages: [
          { role: 'assistant', content: 'Привет!', metadata: {} },
          { role: 'user', content: 'тест', metadata: {} },
          { role: 'assistant', content: 'Полный ответ', metadata: {} },
        ],
      }
    })
    mockStartConversation.mockResolvedValue({
      conversation_id: CONV_ID,
      greeting: 'Привет!',
    })

    // Schedule stream completion after 100ms
    setTimeout(() => {
      streamFinished = true
      streamOnEvent?.('done', {})
      streamResolve?.()
    }, 100)

    // Remount — loadConversation should await _bgStream
    const hook2 = renderHook(() => useChat(AUTH, 'sales', true))
    await act(async () => {
      vi.advanceTimersByTime(200)
      await flush(50)
    })

    expect(hook2.result.current.started).toBe(true)
    // fetchMessages should have been called AFTER stream ended, not before
    expect(fetchCalledBeforeStreamEnd).toBe(false)
  })

  // =========================================================================
  // 6. Background stream timeout (30s)
  // =========================================================================
  it('should timeout after 30s and proceed with partial data', async () => {
    const { result, unmount } = await mountChat()
    await sendMsg(result)
    unmount() // stream still running, never resolves

    mockFetchMessages.mockResolvedValue({
      messages: [
        { role: 'assistant', content: 'Привет!', metadata: {} },
        { role: 'user', content: 'тест', metadata: {} },
        { role: 'assistant', content: 'Частичные данные', metadata: {} },
      ],
    })
    mockStartConversation.mockResolvedValue({
      conversation_id: CONV_ID,
      greeting: 'Привет!',
    })

    // Remount — will await _bgStream (which never resolves)
    const hook2 = renderHook(() => useChat(AUTH, 'sales', true))

    // Advance past the 30s timeout
    await act(async () => {
      vi.advanceTimersByTime(31_000)
      await flush(50)
    })

    // Should have proceeded after timeout
    expect(hook2.result.current.started).toBe(true)
    expect(hook2.result.current.messages.length).toBeGreaterThan(0)

    // Clean up the orphan stream
    await finishStream()
  })

  // =========================================================================
  // 7. _bgStream cleanup after normal completion
  // =========================================================================
  it('should clean up _bgStream after stream completes', async () => {
    const { result } = await mountChat()
    await sendMsg(result)
    await finishStream()

    // After stream completes, switching should be instant (no 30s await)
    mockStartConversation.mockResolvedValueOnce({
      conversation_id: 'conv-999',
      greeting: 'fast',
    })

    const t0 = Date.now()
    await act(async () => {
      result.current.switchConversation('conv-999')
      await flush()
    })

    expect(Date.now() - t0).toBeLessThan(5000)
  })

  // =========================================================================
  // 8. Stream error resolves _bgStream
  // =========================================================================
  it('should resolve _bgStream even if stream errors', async () => {
    const { result, unmount } = await mountChat()
    await sendMsg(result)
    unmount()

    // Stream fails
    await act(async () => {
      streamReject?.(new Error('Network error'))
      await flush()
    })

    // Remount should proceed immediately (no stale await)
    mockFetchMessages.mockResolvedValueOnce({
      messages: [{ role: 'assistant', content: 'Привет!', metadata: {} }],
    })
    const { result: r2 } = await mountChat()
    expect(r2.current.started).toBe(true)
  })

  // =========================================================================
  // 9. Multiple unmount/remount cycles
  // =========================================================================
  it('should handle multiple unmount/remount cycles', async () => {
    // Cycle 1
    const { result: r1, unmount: u1 } = await mountChat()
    await sendMsg(r1)
    u1()
    await finishStream()

    // Cycle 2
    mockFetchMessages.mockResolvedValue({
      messages: [
        { role: 'assistant', content: 'Привет!', metadata: {} },
        { role: 'user', content: 'тест', metadata: {} },
        { role: 'assistant', content: 'Ответ 1', metadata: {} },
      ],
    })
    const { result: r2, unmount: u2 } = await mountChat()
    expect(r2.current.started).toBe(true)
    await sendMsg(r2)
    u2()
    await finishStream()

    // Cycle 3 — full history
    mockFetchMessages.mockResolvedValueOnce({
      messages: [
        { role: 'assistant', content: 'Привет!', metadata: {} },
        { role: 'user', content: 'тест', metadata: {} },
        { role: 'assistant', content: 'Ответ 1', metadata: {} },
        { role: 'user', content: 'тест', metadata: {} },
        { role: 'assistant', content: 'Ответ 2', metadata: {} },
      ],
    })
    const { result: r3 } = await mountChat()
    expect(r3.current.started).toBe(true)
    expect(r3.current.messages).toHaveLength(5)
  })

  // =========================================================================
  // 10. Normal flow without unmount — regression
  // =========================================================================
  it('should work normally without unmount (regression)', async () => {
    const { result } = await mountChat()
    await sendMsg(result)

    await act(() => {
      streamOnEvent?.('token', { text: 'Это ' })
      streamOnEvent?.('token', { text: 'ответ.' })
    })
    await finishStream()

    expect(result.current.typing).toBe(false)
    const msgs = result.current.messages
    const last = msgs[msgs.length - 1]
    expect(last.role).toBe('assistant')
    expect(last.content).toContain('Это ответ.')
  })

  // =========================================================================
  // 11. Double-send guard
  // =========================================================================
  it('should not allow double send while stream is active', async () => {
    const { result } = await mountChat()
    await sendMsg(result)
    const callCount = mockStreamChat.mock.calls.length

    await act(async () => {
      result.current.sendMessage('второе')
      await flush()
    })

    expect(mockStreamChat.mock.calls.length).toBe(callCount)
    await finishStream()
  })
})
