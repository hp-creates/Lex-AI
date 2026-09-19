import { useState, useRef, useEffect, useCallback } from 'react'
import MessageBubble from '../components/MessageBubble'
import LoadingDots from '../components/LoadingDots'
import UploadZone from '../components/UploadZone'
import {
  queryLegal,
  uploadDocument,
  getSessions,
  getSessionMessages,
  renameSession,
  deleteSession,
} from '../lib/api'
import './Dashboard.css'

export default function Dashboard() {
  // --- Chat state ---
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)

  // --- Session state ---
  const [sessions, setSessions] = useState([])
  const [activeSessionId, setActiveSessionId] = useState(null)
  const [isLoadingSessions, setIsLoadingSessions] = useState(true)

  // --- Session menu / rename state ---
  const [menuOpenSessionId, setMenuOpenSessionId] = useState(null)
  const [editingSessionId, setEditingSessionId] = useState(null)
  const [editingTitle, setEditingTitle] = useState('')

  // --- Chat-Specific Documents (scoped to each session) ---
  const [sessionDocsMap, setSessionDocsMap] = useState(() => {
    try {
      const saved = localStorage.getItem('lexai_session_docs')
      return saved ? JSON.parse(saved) : {}
    } catch {
      return {}
    }
  })

  const chatEndRef = useRef(null)
  const textareaRef = useRef(null)
  const renameInputRef = useRef(null)

  // Save sessionDocsMap to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('lexai_session_docs', JSON.stringify(sessionDocsMap))
    } catch (e) {
      console.error('Failed to persist session docs to localStorage:', e)
    }
  }, [sessionDocsMap])

  // Current session's attached documents
  const currentDocs = (activeSessionId ? sessionDocsMap[activeSessionId] : sessionDocsMap['draft']) || []

  // ── Load sessions on mount ─────────────────────────────────────────────────
  useEffect(() => {
    const init = async () => {
      try {
        const sessionList = await getSessions()
        setSessions(sessionList)
        if (sessionList.length > 0) {
          await loadSession(sessionList[0].id)
        }
      } catch (err) {
        console.error('Failed to initialise dashboard:', err)
      } finally {
        setIsLoadingSessions(false)
      }
    }
    init()
  }, [])

  // ── Auto-scroll to bottom ──────────────────────────────────────────────────
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  // ── Close session menu on outside click ────────────────────────────────────
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (!e.target.closest('.session-menu-wrapper')) {
        setMenuOpenSessionId(null)
      }
    }
    document.addEventListener('click', handleClickOutside)
    return () => document.removeEventListener('click', handleClickOutside)
  }, [])

  // Focus rename input when editing starts
  useEffect(() => {
    if (editingSessionId) {
      renameInputRef.current?.focus()
      renameInputRef.current?.select()
    }
  }, [editingSessionId])

  // ── Load a session's messages ──────────────────────────────────────────────
  const loadSession = useCallback(async (sessionId) => {
    setActiveSessionId(sessionId)
    setMessages([])
    setMenuOpenSessionId(null)
    setEditingSessionId(null)
    try {
      const msgs = await getSessionMessages(sessionId)
      const uiMessages = msgs.map((m) => ({
        role: m.role === 'user' ? 'user' : 'assistant',
        text: m.content,
        citations: m.citations || [],
        response_type: m.response_type || 'answer',
      }))
      setMessages(uiMessages)
    } catch (err) {
      console.error('Failed to load session messages:', err)
    }
  }, [])

  // ── New Chat ───────────────────────────────────────────────────────────────
  const handleNewChat = () => {
    setActiveSessionId(null)
    setMessages([])
    setMenuOpenSessionId(null)
    setEditingSessionId(null)
    textareaRef.current?.focus()
  }

  // ── Rename Session ─────────────────────────────────────────────────────────
  const handleStartRename = (session, e) => {
    e?.stopPropagation()
    setMenuOpenSessionId(null)
    setEditingSessionId(session.id)
    setEditingTitle(session.title || 'Untitled Chat')
  }

  const handleSaveRename = async (sessionId, e) => {
    e?.preventDefault()
    e?.stopPropagation()
    const trimmed = editingTitle.trim()
    if (!trimmed) {
      setEditingSessionId(null)
      return
    }

    try {
      await renameSession(sessionId, trimmed)
      setSessions((prev) =>
        prev.map((s) => (s.id === sessionId ? { ...s, title: trimmed } : s))
      )
    } catch (err) {
      console.error('Failed to rename session:', err)
    } finally {
      setEditingSessionId(null)
    }
  }

  const handleCancelRename = (e) => {
    e?.stopPropagation()
    setEditingSessionId(null)
  }

  // ── Delete Session ─────────────────────────────────────────────────────────
  const handleDeleteSession = async (sessionId, e) => {
    e?.stopPropagation()
    setMenuOpenSessionId(null)
    try {
      await deleteSession(sessionId)
      setSessions((prev) => prev.filter((s) => s.id !== sessionId))

      // Clean up docs for deleted session
      setSessionDocsMap((prev) => {
        const copy = { ...prev }
        delete copy[sessionId]
        return copy
      })

      // If active session was deleted, clear chat or switch to new chat
      if (activeSessionId === sessionId) {
        handleNewChat()
      }
    } catch (err) {
      console.error('Failed to delete session:', err)
    }
  }

  // ── Send message ───────────────────────────────────────────────────────────
  const handleSend = async () => {
    const question = input.trim()
    if (!question || isLoading) return

    setMessages((prev) => [...prev, { role: 'user', text: question }])
    setInput('')
    setIsLoading(true)

    try {
      // Pass the active chat's document ID (if one is attached to this chat)
      const attachedDocId = currentDocs[0]?.doc_id || ''
      const data = await queryLegal(question, attachedDocId, activeSessionId)

      if (data.session_id && !activeSessionId) {
        const newId = data.session_id
        setActiveSessionId(newId)

        // Migrate draft docs to the new session ID
        setSessionDocsMap((prev) => {
          const draftDocs = prev['draft'] || []
          const updated = { ...prev, [newId]: draftDocs }
          delete updated['draft']
          return updated
        })

        const updatedSessions = await getSessions()
        setSessions(updatedSessions)
      }

      setMessages((prev) => [...prev, {
        role: 'assistant',
        text: data.answer,
        citations: data.citations || [],
        response_type: data.response_type,
        confidence: data.confidence,
        disclaimer: data.disclaimer,
      }])
    } catch (err) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        text: `Error: ${err.response?.data?.detail || err.message || 'Could not reach the server.'}`,
        response_type: 'error',
        citations: [],
      }])
    } finally {
      setIsLoading(false)
    }
  }

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // ── Upload ─────────────────────────────────────────────────────────────────
  const handleUpload = async (file) => {
    setIsUploading(true)
    try {
      const data = await uploadDocument(file)
      const docItem = {
        doc_id: data.doc_id,
        filename: data.filename,
        chunk_count: data.chunk_count,
      }

      const key = activeSessionId || 'draft'
      setSessionDocsMap((prev) => ({
        ...prev,
        [key]: [...(prev[key] || []), docItem],
      }))

      setMessages((prev) => [...prev, {
        role: 'assistant',
        text: `Attached **"${data.filename}"** to this chat (${data.chunk_count} sections indexed). All questions in this chat will now reference it.`,
        response_type: 'answer',
        citations: [],
      }])
    } catch (err) {
      setMessages((prev) => [...prev, {
        role: 'assistant',
        text: `Upload failed: ${err.response?.data?.detail || err.message}`,
        response_type: 'error',
        citations: [],
      }])
    } finally {
      setIsUploading(false)
    }
  }

  // ── Relative time formatter ────────────────────────────────────────────────
  const formatSessionDate = (isoString) => {
    const d = new Date(isoString)
    const diffMs = Date.now() - d
    const mins = Math.floor(diffMs / 60000)
    const hrs = Math.floor(diffMs / 3600000)
    const days = Math.floor(diffMs / 86400000)
    if (mins < 1) return 'Just now'
    if (mins < 60) return `${mins}m ago`
    if (hrs < 24) return `${hrs}h ago`
    if (days === 1) return 'Yesterday'
    return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
  }

  return (
    <div className="dashboard">

      {/* ── Sidebar ──────────────────────────────────────────────────────── */}
      <aside className="sidebar">
        <button className="new-chat-btn" onClick={handleNewChat}>
          <svg className="sidebar-btn-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 5v14M5 12h14"/>
          </svg>
          New Chat
        </button>

        {/* Sessions */}
        <div className="sidebar-section">
          <p className="sidebar-label">Recent Chats</p>
          {isLoadingSessions ? (
            <div className="sidebar-empty-hint">Loading...</div>
          ) : sessions.length === 0 ? (
            <div className="sidebar-empty-hint">No chats yet.<br />Ask your first question!</div>
          ) : (
            <div className="sessions-list">
              {sessions.map((s) => (
                <div
                  key={s.id}
                  className={`session-item-wrapper ${activeSessionId === s.id ? 'active' : ''} ${menuOpenSessionId === s.id ? 'menu-open' : ''}`}
                  onContextMenu={(e) => {
                    e.preventDefault()
                    e.stopPropagation()
                    setMenuOpenSessionId(s.id === menuOpenSessionId ? null : s.id)
                  }}
                >
                  {editingSessionId === s.id ? (
                    <form
                      className="session-rename-form"
                      onSubmit={(e) => handleSaveRename(s.id, e)}
                    >
                      <input
                        ref={renameInputRef}
                        type="text"
                        className="session-rename-input"
                        value={editingTitle}
                        onChange={(e) => setEditingTitle(e.target.value)}
                        onKeyDown={(e) => {
                          if (e.key === 'Escape') handleCancelRename(e)
                        }}
                      />
                      <button type="submit" className="session-rename-btn save" title="Save">
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12"/>
                        </svg>
                      </button>
                      <button
                        type="button"
                        className="session-rename-btn cancel"
                        onClick={handleCancelRename}
                        title="Cancel"
                      >
                        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                          <line x1="18" y1="6" x2="6" y2="18"/>
                          <line x1="6" y1="6" x2="18" y2="18"/>
                        </svg>
                      </button>
                    </form>
                  ) : (
                    <>
                      <button
                        className="session-item"
                        onClick={() => loadSession(s.id)}
                        title={s.title}
                      >
                        <svg className="session-icon" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>
                        </svg>
                        <span className="session-info">
                          <span className="session-title">{s.title || 'Untitled Chat'}</span>
                          <span className="session-date">{formatSessionDate(s.created_at)}</span>
                        </span>
                      </button>

                      <div className="session-menu-wrapper">
                        <button
                          type="button"
                          className={`session-menu-trigger ${menuOpenSessionId === s.id ? 'open' : ''}`}
                          onClick={(e) => {
                            e.preventDefault()
                            e.stopPropagation()
                            setMenuOpenSessionId(menuOpenSessionId === s.id ? null : s.id)
                          }}
                          title="Chat options"
                        >
                          ⋮
                        </button>

                        {menuOpenSessionId === s.id && (
                          <div
                            className="session-dropdown"
                            onClick={(e) => e.stopPropagation()}
                          >
                            <button
                              type="button"
                              className="session-dropdown-item"
                              onClick={(e) => handleStartRename(s, e)}
                            >
                              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <path d="M12 20h9"/>
                                <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z"/>
                              </svg>
                              Rename
                            </button>
                            <button
                              type="button"
                              className="session-dropdown-item danger"
                              onClick={(e) => handleDeleteSession(s.id, e)}
                            >
                              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                                <polyline points="3 6 5 6 21 6"/>
                                <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"/>
                              </svg>
                              Delete
                            </button>
                          </div>
                        )}
                      </div>
                    </>
                  )}
                </div>
              ))}
            </div>
          )}
        </div>

        <div className="sidebar-divider" />

        {/* Documents — Chat-Specific */}
        <div className="sidebar-section sidebar-docs-section">
          <p className="sidebar-label">Chat Documents</p>
          <p className="sidebar-docs-hint">Attached to this conversation only</p>
          <UploadZone onUpload={handleUpload} isUploading={isUploading} />
          {currentDocs.length > 0 && (
            <div className="sidebar-docs">
              {currentDocs.map((doc) => (
                <div key={doc.doc_id} className="sidebar-doc">
                  <span className="sidebar-doc-name">
                    <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 6, verticalAlign: 'middle' }}>
                      <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                      <polyline points="14 2 14 8 20 8"/>
                    </svg>
                    {doc.filename}
                  </span>
                  <span className="sidebar-doc-chunks">{doc.chunk_count} chunks</span>
                </div>
              ))}
            </div>
          )}
        </div>
      </aside>

      {/* ── Chat Area ────────────────────────────────────────────────────── */}
      <main className="chat-area">
        {/* Claude-style document banner inside active conversation */}
        {currentDocs.length > 0 && (
          <div className="chat-doc-banner">
            <div className="chat-doc-banner-icon">
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/>
                <polyline points="14 2 14 8 20 8"/>
              </svg>
            </div>
            <div className="chat-doc-banner-info">
              <span className="chat-doc-banner-title">
                {currentDocs.map((d) => d.filename).join(', ')}
              </span>
              <span className="chat-doc-banner-sub">
                {currentDocs.reduce((acc, d) => acc + d.chunk_count, 0)} sections indexed • Context active for this chat
              </span>
            </div>
          </div>
        )}

        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="chat-empty">
              <div className="chat-empty-icon-wrap">
                <svg width="42" height="42" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/>
                  <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/>
                  <path d="M7 21h10"/>
                  <path d="M12 3v18"/>
                  <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>
                </svg>
              </div>
              <h2>Ask about Indian Law</h2>
              <p>
                Ask any question about your rights under Indian law.
                {currentDocs.length > 0 && (
                  <> Questions in this chat will reference <strong>{currentDocs[0].filename}</strong>.</>
                )}
              </p>
              <div className="chat-suggestions">
                {[
                  'What are my rights if police arrest me?',
                  'Is DigiLocker valid as an ID proof?',
                  'What does Section 302 IPC say?',
                ].map((q) => (
                  <button key={q} className="btn btn-secondary" onClick={() => setInput(q)}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg, i) => (
            <MessageBubble key={i} message={msg} />
          ))}

          {isLoading && (
            <div className="message-bubble assistant">
              <div className="message-avatar">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="m16 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/>
                  <path d="m2 16 3-8 3 8c-.87.65-1.92 1-3 1s-2.13-.35-3-1Z"/>
                  <path d="M7 21h10"/>
                  <path d="M12 3v18"/>
                  <path d="M3 7h2c2 0 5-1 7-2 2 1 5 2 7 2h2"/>
                </svg>
              </div>
              <LoadingDots />
            </div>
          )}
          <div ref={chatEndRef} />
        </div>

        {/* Input Bar */}
        <div className="chat-input-bar">
          {currentDocs.length > 0 && (
            <div className="chat-context-badge">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" style={{ marginRight: 4, verticalAlign: 'middle' }}>
                <path d="m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48"/>
              </svg>
              {currentDocs.map((d) => d.filename).join(', ')} attached to this chat
            </div>
          )}
          <div className="chat-input-row">
            <textarea
              ref={textareaRef}
              className="input chat-input"
              placeholder="Ask about your legal rights..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={isLoading}
            />
            <button
              id="send-btn"
              className="btn btn-primary chat-send"
              onClick={handleSend}
              disabled={isLoading || !input.trim()}
            >
              Send
            </button>
          </div>
        </div>
      </main>
    </div>
  )
}

