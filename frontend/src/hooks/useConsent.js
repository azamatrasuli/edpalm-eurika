import { useState, useEffect, useRef, useCallback } from 'react'
import { fetchConsentStatus, grantConsent } from '../api/client'

const CACHE_KEY = 'eurika_consent_granted'

/**
 * Hook for first-visit consent check.
 *
 * Returns:
 * - consentReady: true when check is done and consent is given (safe to show chat)
 * - consentNeeded: true when consent screen should be shown
 * - consentChecking: true during initial API check
 * - acceptConsents(purposeIds): grant selected consents and proceed
 * - acceptLoading: true during grant API calls
 */
export function useConsent(auth) {
  const [consentReady, setConsentReady] = useState(false)
  const [consentNeeded, setConsentNeeded] = useState(false)
  const [consentChecking, setConsentChecking] = useState(true)
  const [acceptLoading, setAcceptLoading] = useState(false)
  const initRef = useRef(false)

  // Check consent on mount
  useEffect(() => {
    if (!auth || initRef.current) return
    initRef.current = true

    // Fast path: check sessionStorage cache
    try {
      const cached = sessionStorage.getItem(CACHE_KEY)
      if (cached === 'true') {
        setConsentReady(true)
        setConsentChecking(false)
        return
      }
    } catch { /* sessionStorage not available */ }

    // Slow path: check API
    ;(async () => {
      try {
        const data = await fetchConsentStatus(auth)
        if (data.all_required_granted) {
          setConsentReady(true)
          try { sessionStorage.setItem(CACHE_KEY, 'true') } catch {}
        } else {
          setConsentNeeded(true)
        }
      } catch {
        // On error, let user through (don't block chat for API failures)
        setConsentReady(true)
      } finally {
        setConsentChecking(false)
      }
    })()
  }, [auth])

  // Grant selected consents
  const acceptConsents = useCallback(async (purposeIds) => {
    if (!auth) return
    setAcceptLoading(true)
    try {
      // Grant all selected in parallel
      await Promise.all(
        purposeIds.map(id => grantConsent(auth, id))
      )
      setConsentNeeded(false)
      setConsentReady(true)
      try { sessionStorage.setItem(CACHE_KEY, 'true') } catch {}
    } catch {
      // If grant fails, still let user through to avoid blocking
      setConsentNeeded(false)
      setConsentReady(true)
    } finally {
      setAcceptLoading(false)
    }
  }, [auth])

  return {
    consentReady,
    consentNeeded,
    consentChecking,
    acceptConsents,
    acceptLoading,
  }
}
