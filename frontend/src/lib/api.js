import axios from 'axios'
import { supabase } from './supabase'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 120000, // 120s default — LangGraph pipeline can take 40-60s
  headers: { 'Content-Type': 'application/json' },
})

// Inject Supabase JWT into every request automatically
api.interceptors.request.use(async (config) => {
  const { data: { session } } = await supabase.auth.getSession()
  if (session?.access_token) {
    config.headers['Authorization'] = `Bearer ${session.access_token}`
  }
  return config
})

/**
 * POST /query — ask a legal question
 */
export const queryLegal = async (question, docId = '', sessionId = null) => {
  const payload = { question, doc_id: docId }
  if (sessionId) payload.session_id = sessionId

  const { data } = await api.post('/query', payload, {
    timeout: 120000, // 120s — allows full pipeline with rewrite_query fallback
  })
  return data
}

/**
 * POST /upload — upload a document (PDF, TXT, image)
 */
export const uploadDocument = async (file, sourceName = '') => {
  const formData = new FormData()
  formData.append('file', file)
  if (sourceName) formData.append('source_name', sourceName)

  const { data } = await api.post('/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 120000,
  })
  return data
}

/**
 * GET /health — check API status
 */
export const getHealth = async () => {
  const { data } = await api.get('/health')
  return data
}

/**
 * GET /documents — list user's uploaded documents
 */
export const getDocuments = async () => {
  const { data } = await api.get('/documents')
  return data
}

/**
 * DELETE /documents/{doc_id} — delete a user document
 */
export const deleteDocument = async (docId) => {
  const { data } = await api.delete(`/documents/${docId}`)
  return data
}

/**
 * GET /sessions — list all chat sessions for the current user
 */
export const getSessions = async () => {
  const { data } = await api.get('/sessions')
  return data
}

/**
 * GET /sessions/{id}/messages — load all messages for a session
 */
export const getSessionMessages = async (sessionId) => {
  const { data } = await api.get(`/sessions/${sessionId}/messages`)
  return data
}

/**
 * PATCH /sessions/{id} — rename a chat session
 */
export const renameSession = async (sessionId, title) => {
  const { data } = await api.patch(`/sessions/${sessionId}`, { title })
  return data
}

/**
 * DELETE /sessions/{id} — delete a chat session
 */
export const deleteSession = async (sessionId) => {
  const { data } = await api.delete(`/sessions/${sessionId}`)
  return data
}

export default api
