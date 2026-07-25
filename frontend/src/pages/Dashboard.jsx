import { useState, useRef, useEffect } from 'react'
import MessageBubble from '../components/MessageBubble'
import LoadingDots from '../components/LoadingDots'
import UploadZone from '../components/UploadZone'
import { queryLegal, uploadDocument, getDocuments } from '../lib/api'
import './Dashboard.css'

export default function Dashboard() {
  const [messages, setMessages] = useState([])
  const [input, setInput] = useState('')
  const [isLoading, setIsLoading] = useState(false)
  const [isUploading, setIsUploading] = useState(false)
  const [uploadedDocs, setUploadedDocs] = useState([])
  const [selectedDoc, setSelectedDoc] = useState('')
  const chatEndRef = useRef(null)

  // Load uploaded documents on mount so sidebar persists on reload
  useEffect(() => {
    const loadDocs = async () => {
      try {
        const docs = await getDocuments()
        setUploadedDocs(docs)
      } catch (err) {
        console.error('Failed to load documents for sidebar:', err)
      }
    }
    loadDocs()
  }, [])

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    chatEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, isLoading])

  const handleSend = async () => {
    const question = input.trim()
    if (!question || isLoading) return

    // Add user message
    const userMsg = { role: 'user', text: question }
    setMessages((prev) => [...prev, userMsg])
    setInput('')
    setIsLoading(true)

    try {
      const data = await queryLegal(question, selectedDoc)

      const assistantMsg = {
        role: 'assistant',
        text: data.answer,
        citations: data.citations || [],
        response_type: data.response_type,
        confidence: data.confidence,
        disclaimer: data.disclaimer,
      }
      setMessages((prev) => [...prev, assistantMsg])
    } catch (err) {
      const errorMsg = {
        role: 'assistant',
        text: `Error: ${err.response?.data?.detail || err.message || 'Could not reach the server. Is the backend running?'}`,
        response_type: 'error',
        citations: [],
      }
      setMessages((prev) => [...prev, errorMsg])
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

  const handleUpload = async (file) => {
    setIsUploading(true)
    try {
      const data = await uploadDocument(file)
      setUploadedDocs((prev) => [
        ...prev,
        { doc_id: data.doc_id, filename: data.filename, chunk_count: data.chunk_count },
      ])

      const sysMsg = {
        role: 'assistant',
        text: `Document "${data.filename}" uploaded successfully!\n${data.chunk_count} sections indexed. You can now ask questions about it.`,
        response_type: 'answer',
        citations: [],
      }
      setMessages((prev) => [...prev, sysMsg])
    } catch (err) {
      const errorMsg = {
        role: 'assistant',
        text: `Upload failed: ${err.response?.data?.detail || err.message}`,
        response_type: 'error',
        citations: [],
      }
      setMessages((prev) => [...prev, errorMsg])
    } finally {
      setIsUploading(false)
    }
  }

  return (
    <div className="dashboard">
      {/* Sidebar */}
      <aside className="sidebar">
        <UploadZone onUpload={handleUpload} isUploading={isUploading} />

        {uploadedDocs.length > 0 && (
          <div className="sidebar-docs">
            <h3 className="sidebar-title">Uploaded Documents</h3>
            {uploadedDocs.map((doc) => (
              <div
                key={doc.doc_id}
                className={`sidebar-doc ${selectedDoc === doc.doc_id ? 'selected' : ''}`}
                onClick={() =>
                  setSelectedDoc(selectedDoc === doc.doc_id ? '' : doc.doc_id)
                }
              >
                <span className="sidebar-doc-name">📄 {doc.filename}</span>
                <span className="sidebar-doc-chunks">{doc.chunk_count} chunks</span>
              </div>
            ))}
            {selectedDoc && (
              <button
                className="btn btn-secondary"
                style={{ width: '100%', marginTop: 8 }}
                onClick={() => setSelectedDoc('')}
              >
                Clear selection (search all)
              </button>
            )}
          </div>
        )}
      </aside>

      {/* Chat Area */}
      <main className="chat-area">
        <div className="chat-messages">
          {messages.length === 0 && (
            <div className="chat-empty">
              <span className="chat-empty-icon">⚖</span>
              <h2>Ask about Indian Law</h2>
              <p>
                Upload a legal document or ask any question about your rights
                under Indian law. I'll find the relevant sections and cite my
                sources.
              </p>
              <div className="chat-suggestions">
                {[
                  'What are my rights if police arrest me?',
                  'Is DigiLocker valid as an ID proof?',
                  'What does Section 302 IPC say?',
                ].map((q) => (
                  <button
                    key={q}
                    className="btn btn-secondary"
                    onClick={() => {
                      setInput(q)
                    }}
                  >
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
              <div className="message-avatar">⚖</div>
              <LoadingDots />
            </div>
          )}

          <div ref={chatEndRef} />
        </div>

        {/* Input */}
        <div className="chat-input-bar">
          {selectedDoc && (
            <div className="chat-context-badge badge badge-info">
              Searching: {uploadedDocs.find((d) => d.doc_id === selectedDoc)?.filename || 'selected doc'}
            </div>
          )}
          <div className="chat-input-row">
            <textarea
              className="input chat-input"
              placeholder="Ask about your legal rights..."
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              rows={1}
              disabled={isLoading}
            />
            <button
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
