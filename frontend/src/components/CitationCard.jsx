import { useState } from 'react'
import './CitationCard.css'

export default function CitationCard({ citation }) {
  const [expanded, setExpanded] = useState(false)

  const confidence = Math.round((citation.confidence || 0) * 100)
  const confidenceClass =
    confidence >= 80 ? 'high' : confidence >= 50 ? 'medium' : 'low'

  return (
    <div className={`citation-card ${expanded ? 'expanded' : ''}`} onClick={() => setExpanded(!expanded)}>
      <div className="citation-header">
        <div className="citation-source">
          <span className="citation-icon">📚</span>
          <span className="citation-act">{citation.act_short || citation.source || 'Source'}</span>
          {citation.section && (
            <span className="citation-section">{citation.section}</span>
          )}
        </div>
        <span className={`citation-confidence ${confidenceClass}`}>
          {confidence}%
        </span>
      </div>

      {expanded && citation.text && (
        <div className="citation-body">
          <p className="citation-text">"{citation.text}"</p>
          <span className="citation-source-full">{citation.source}</span>
        </div>
      )}

      <span className="citation-toggle">{expanded ? '▲ Collapse' : '▼ View source'}</span>
    </div>
  )
}
