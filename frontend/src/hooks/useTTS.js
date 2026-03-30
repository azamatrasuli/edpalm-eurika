import { useCallback, useEffect, useRef, useState } from 'react'

/**
 * Hook for text-to-speech playback using browser-native Web Speech API.
 *
 * Returns:
 *   play(messageId, text) — start/pause/resume
 *   stop()               — stop and reset
 *   playingId            — id of the message currently playing (or null)
 *   ttsState             — 'idle' | 'loading' | 'playing' | 'paused'
 *   supported            — boolean: is speechSynthesis available at all
 *
 * NOTE: Chrome may pause utterances longer than ~15 seconds.
 * A periodic pause/resume workaround can be added in a follow-up.
 */
export function useTTS(_auth, { onError } = {}) {
  const [playingId, setPlayingId] = useState(null)
  const [ttsState, setTtsState] = useState('idle')
  const [supported, setSupported] = useState(false)
  const utteranceRef = useRef(null)

  useEffect(() => {
    setSupported(typeof window !== 'undefined' && 'speechSynthesis' in window)
  }, [])

  const stop = useCallback(() => {
    if (typeof window !== 'undefined' && window.speechSynthesis) {
      window.speechSynthesis.cancel()
    }
    utteranceRef.current = null
    setPlayingId(null)
    setTtsState('idle')
  }, [])

  const play = useCallback((messageId, text) => {
    if (!window.speechSynthesis) {
      onError?.('Браузер не поддерживает озвучивание текста')
      return
    }

    // Toggle pause/resume for the same message
    if (playingId === messageId) {
      if (ttsState === 'playing') {
        window.speechSynthesis.pause()
        setTtsState('paused')
        return
      }
      if (ttsState === 'paused') {
        window.speechSynthesis.resume()
        setTtsState('playing')
        return
      }
    }

    // Stop any current playback before starting new
    stop()

    setPlayingId(messageId)
    setTtsState('loading')

    const utterance = new SpeechSynthesisUtterance(text)
    utterance.lang = 'ru-RU'
    utterance.rate = 1.0

    // Try to pick a Russian voice if available
    const voices = window.speechSynthesis.getVoices()
    const ruVoice = voices.find((v) => v.lang.startsWith('ru'))
    if (ruVoice) utterance.voice = ruVoice

    utterance.onstart = () => setTtsState('playing')
    utterance.onend = () => {
      utteranceRef.current = null
      setPlayingId(null)
      setTtsState('idle')
    }
    utterance.onerror = (e) => {
      if (e.error === 'canceled') return
      utteranceRef.current = null
      setPlayingId(null)
      setTtsState('idle')
      onError?.('Не удалось озвучить текст')
    }

    utteranceRef.current = utterance
    window.speechSynthesis.speak(utterance)
  }, [playingId, ttsState, stop, onError])

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (typeof window !== 'undefined' && window.speechSynthesis) {
        window.speechSynthesis.cancel()
      }
    }
  }, [])

  return { play, stop, playingId, ttsState, supported }
}
