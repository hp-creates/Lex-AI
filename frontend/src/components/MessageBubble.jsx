import ReactMarkdown from 'react-markdown'
import CitationCard from './CitationCard'
import './MessageBubble.css'

export default function MessageBubble({ message }) {
  const isUser = message.role === 'user'
  const isRejection = message.response_type === 'rejection'
  const isNoContext = message.response_type === 'no_context'

  return (
    <div className={`message-bubble ${isUser ? 'user' : 'assistant'}`}>
      <div className="message-avatar">
        {isUser ? '👤' : '⚖'}
      </div>

      <div className="message-content">
        <span className="message-role">{isUser ? 'You' : 'LexAI'}</span>

        {(isRejection || isNoContext) && (
          <div className={`message-banner ${isRejection ? 'rejection' : 'no-context'}`}>
            {isRejection ? '🚫 Off-topic question' : '⚠ No matching context found'}
          </div>
        )}

        <div className="message-text">
          {isUser ? (
            message.text
          ) : (
            <ReactMarkdown
              components={{
                h2: ({ children }) => <h2 className="md-h2">{children}</h2>,
                h3: ({ children }) => <h3 className="md-h3">{children}</h3>,
                p:  ({ children }) => <p className="md-p">{children}</p>,
                li: ({ children }) => <li className="md-li">{children}</li>,
                strong: ({ children }) => <strong className="md-strong">{children}</strong>,
                blockquote: ({ children }) => <blockquote className="md-blockquote">{children}</blockquote>,
              }}
            >
              {message.text}
            </ReactMarkdown>
          )}
        </div>

        {!isUser && message.citations && message.citations.length > 0 && (
          <div className="message-citations">
            <span className="citations-label">Sources ({message.citations.length})</span>
            {message.citations.map((citation, i) => (
              <CitationCard key={i} citation={citation} />
            ))}
          </div>
        )}

        {!isUser && message.disclaimer && (
          <div className="message-disclaimer">{message.disclaimer}</div>
        )}
      </div>
    </div>
  )
}
