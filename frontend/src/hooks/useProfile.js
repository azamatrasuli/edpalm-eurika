import { useState, useEffect, useRef, useCallback } from 'react'
import {
  fetchProfile,
  updateProfile,
  fetchMemories,
  deleteMemory,
  clearMemories,
  fetchConsentStatus,
  grantConsent,
  revokeConsent,
  requestExport,
  downloadExport,
  requestDeletion,
  cancelDeletion,
  getDeletionStatus,
} from '../api/client'

export function useProfile(auth) {
  const [profile, setProfile] = useState(null)
  const [memories, setMemories] = useState([])
  const [consents, setConsents] = useState([])
  const [allRequiredGranted, setAllRequiredGranted] = useState(false)
  const [deletion, setDeletion] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const initRef = useRef(false)

  // ---- Load all data -------------------------------------------------------

  const loadAll = useCallback(async () => {
    if (!auth) return
    setLoading(true)
    setError('')
    try {
      const [profileData, consentData, deletionData] = await Promise.all([
        fetchProfile(auth),
        fetchConsentStatus(auth).catch(() => ({ consents: [], all_required_granted: false })),
        getDeletionStatus(auth).catch(() => ({ has_pending: false })),
      ])
      setProfile(profileData)
      setMemories(profileData.memories || [])
      setConsents(consentData.consents || [])
      setAllRequiredGranted(consentData.all_required_granted || false)
      setDeletion(deletionData.has_pending ? deletionData : null)
    } catch (e) {
      setError(e.message || 'Не удалось загрузить профиль')
    } finally {
      setLoading(false)
    }
  }, [auth])

  useEffect(() => {
    if (!auth || initRef.current) return
    initRef.current = true
    loadAll()
  }, [auth, loadAll])

  // ---- Profile actions -----------------------------------------------------

  const updateName = useCallback(async (name) => {
    try {
      await updateProfile(auth, { display_name: name })
      setProfile(prev => prev ? { ...prev, display_name: name } : prev)
    } catch (e) {
      setError(e.message)
    }
  }, [auth])

  // ---- Memory actions ------------------------------------------------------

  const removeMemory = useCallback(async (atomId) => {
    try {
      await deleteMemory(auth, atomId)
      setMemories(prev => prev.filter(m => m.id !== atomId))
      setProfile(prev => prev ? { ...prev, stats: { ...prev.stats, memory_count: Math.max(0, (prev.stats?.memory_count || 1) - 1) } } : prev)
    } catch (e) {
      setError(e.message)
    }
  }, [auth])

  const clearAllMemories = useCallback(async () => {
    try {
      await clearMemories(auth)
      setMemories([])
      setProfile(prev => prev ? { ...prev, stats: { ...prev.stats, memory_count: 0 } } : prev)
    } catch (e) {
      setError(e.message)
    }
  }, [auth])

  // ---- Consent actions -----------------------------------------------------

  const toggleConsent = useCallback(async (purposeId, granted) => {
    try {
      if (granted) {
        await grantConsent(auth, purposeId)
      } else {
        await revokeConsent(auth, purposeId)
      }
      setConsents(prev => prev.map(c =>
        c.purpose_id === purposeId
          ? { ...c, granted, granted_at: granted ? new Date().toISOString() : c.granted_at, revoked_at: granted ? null : new Date().toISOString() }
          : c
      ))
      // If ai_memory revoked, clear memories in UI
      if (purposeId === 'ai_memory' && !granted) {
        setMemories([])
      }
    } catch (e) {
      setError(e.message)
    }
  }, [auth])

  // ---- Export actions -------------------------------------------------------

  const doExport = useCallback(async () => {
    try {
      const { request_id } = await requestExport(auth)
      const data = await downloadExport(auth, request_id)
      // Trigger browser download
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = 'eurika_my_data.json'
      a.click()
      URL.revokeObjectURL(url)
    } catch (e) {
      setError(e.message)
    }
  }, [auth])

  // ---- Deletion actions ----------------------------------------------------

  const doRequestDeletion = useCallback(async (reason) => {
    try {
      const result = await requestDeletion(auth, reason)
      setDeletion(result)
    } catch (e) {
      setError(e.message)
    }
  }, [auth])

  const doCancelDeletion = useCallback(async () => {
    try {
      await cancelDeletion(auth)
      setDeletion(null)
    } catch (e) {
      setError(e.message)
    }
  }, [auth])

  return {
    profile, memories, consents, allRequiredGranted, deletion,
    loading, error,
    updateName, removeMemory, clearAllMemories,
    toggleConsent,
    doExport, doRequestDeletion, doCancelDeletion,
    reload: loadAll,
  }
}
