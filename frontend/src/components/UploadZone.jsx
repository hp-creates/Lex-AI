import { useState, useRef } from 'react'
import './UploadZone.css'

export default function UploadZone({ onUpload, isUploading }) {
  const [isDragging, setIsDragging] = useState(false)
  const fileInputRef = useRef(null)

  const ACCEPTED_TYPES = ['.pdf', '.txt', '.md', '.png', '.jpg', '.jpeg']
  const MAX_SIZE_MB = 10

  const handleFiles = (files) => {
    const file = files[0]
    if (!file) return

    const ext = '.' + file.name.split('.').pop().toLowerCase()
    if (!ACCEPTED_TYPES.includes(ext)) {
      alert(`Unsupported file type: ${ext}\nAccepted: ${ACCEPTED_TYPES.join(', ')}`)
      return
    }

    if (file.size > MAX_SIZE_MB * 1024 * 1024) {
      alert(`File too large (${(file.size / 1024 / 1024).toFixed(1)}MB). Max: ${MAX_SIZE_MB}MB`)
      return
    }

    onUpload(file)
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const handleDragOver = (e) => {
    e.preventDefault()
    setIsDragging(true)
  }

  return (
    <div
      className={`upload-zone ${isDragging ? 'dragging' : ''} ${isUploading ? 'uploading' : ''}`}
      onDrop={handleDrop}
      onDragOver={handleDragOver}
      onDragLeave={() => setIsDragging(false)}
      onClick={() => !isUploading && fileInputRef.current?.click()}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept={ACCEPTED_TYPES.join(',')}
        onChange={(e) => handleFiles(e.target.files)}
        hidden
      />

      {isUploading ? (
        <div className="upload-status">
          <div className="upload-spinner" />
          <p>Processing document...</p>
        </div>
      ) : (
        <div className="upload-prompt">
          <span className="upload-icon">📄</span>
          <p className="upload-title">
            {isDragging ? 'Drop your file here' : 'Upload a legal document'}
          </p>
          <p className="upload-subtitle">
            PDF, TXT, MD, PNG, JPG — up to {MAX_SIZE_MB}MB
          </p>
        </div>
      )}
    </div>
  )
}
