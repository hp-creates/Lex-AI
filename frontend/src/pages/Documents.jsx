import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import UploadZone from '../components/UploadZone'
import { uploadDocument, getDocuments, deleteDocument } from '../lib/api'
import './Documents.css'

function fileIcon(type) {
  if (type === 'pdf') return '📕'
  if (type === 'image') return '🖼'
  return '📄'
}

export default function Documents() {
  const [documents, setDocuments] = useState([])
  const [isLoading, setIsLoading] = useState(true)
  const [isUploading, setIsUploading] = useState(false)
  const [deletingId, setDeletingId] = useState(null)
  const navigate = useNavigate()

  // Load documents from backend on mount
  useEffect(() => {
    const load = async () => {
      try {
        const docs = await getDocuments()
        setDocuments(docs)
      } catch (err) {
        console.error('Failed to load documents:', err)
      } finally {
        setIsLoading(false)
      }
    }
    load()
  }, [])

  const handleUpload = async (file) => {
    setIsUploading(true)
    try {
      const data = await uploadDocument(file)
      // Add to top of list immediately without re-fetching
      setDocuments((prev) => [
        {
          doc_id: data.doc_id,
          filename: data.filename,
          file_type: data.file_type,
          chunk_count: data.chunk_count,
          total_chars: data.total_chars,
          source_name: data.filename,
          created_at: new Date().toISOString(),
        },
        ...prev,
      ])
    } catch (err) {
      alert(`Upload failed: ${err.response?.data?.detail || err.message}`)
    } finally {
      setIsUploading(false)
    }
  }

  const handleDelete = async (docId) => {
    if (!window.confirm('Delete this document? All indexed chunks will be removed.')) return
    setDeletingId(docId)
    try {
      await deleteDocument(docId)
      setDocuments((prev) => prev.filter((d) => d.doc_id !== docId))
    } catch (err) {
      alert(`Delete failed: ${err.response?.data?.detail || err.message}`)
    } finally {
      setDeletingId(null)
    }
  }

  const handleAskQuestion = (docId) => {
    navigate('/dashboard')
  }

  return (
    <div className="documents-page">
      <div className="documents-header">
        <h1>Your Documents</h1>
        <p className="documents-subtitle">
          Upload legal documents to ask questions about them
        </p>
      </div>

      <div className="documents-upload-area">
        <UploadZone onUpload={handleUpload} isUploading={isUploading} />
      </div>

      {isLoading ? (
        <div className="documents-loading">
          <div className="docs-spinner" />
          <p>Loading your documents...</p>
        </div>
      ) : documents.length === 0 ? (
        <div className="documents-empty">
          <span className="documents-empty-icon">📁</span>
          <h3>No documents yet</h3>
          <p>Upload your first legal document to get started.</p>
        </div>
      ) : (
        <div className="documents-grid">
          {documents.map((doc) => (
            <div key={doc.doc_id} className="card document-card">
              <div className="doc-card-header">
                <span className="doc-card-icon">{fileIcon(doc.file_type)}</span>
                <div className="doc-card-info">
                  <h4 className="doc-card-name">{doc.source_name || doc.filename}</h4>
                  <span className="doc-card-meta">
                    {doc.chunk_count} sections &middot; {((doc.total_chars || 0) / 1000).toFixed(1)}K chars
                  </span>
                </div>
                <span className="badge badge-success">Ready</span>
              </div>

              <div className="doc-card-stats">
                <div className="doc-stat">
                  <span className="doc-stat-label">Type</span>
                  <span className="doc-stat-value">{doc.file_type?.toUpperCase()}</span>
                </div>
                <div className="doc-stat">
                  <span className="doc-stat-label">Uploaded</span>
                  <span className="doc-stat-value">
                    {new Date(doc.created_at).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })}
                  </span>
                </div>
              </div>

              <div className="doc-card-actions">
                <button
                  className="btn btn-primary"
                  onClick={() => handleAskQuestion(doc.doc_id)}
                >
                  Ask a Question
                </button>
                <button
                  className="btn btn-danger"
                  onClick={() => handleDelete(doc.doc_id)}
                  disabled={deletingId === doc.doc_id}
                >
                  {deletingId === doc.doc_id ? 'Deleting...' : 'Delete'}
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
