import axios from 'axios'
import { supabase } from './supabase'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '/api/v1',
  timeout: 60000,
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
export const queryLegal = async (question, docId = '') => {
  const { data } = await api.post('/query', { question, doc_id: docId })
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

export default api
