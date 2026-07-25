import { Link } from 'react-router-dom'
import './Landing.css'

export default function Landing() {
  return (
    <div className="landing">
      {/* Hero Section */}
      <section className="hero">
        <div className="hero-glow" />
        <div className="hero-content">
          <span className="hero-badge badge badge-info">AI-Powered Legal Assistant</span>
          <h1 className="hero-title">
            Know your rights.
            <br />
            <span className="hero-highlight">In plain English.</span>
          </h1>
          <p className="hero-subtitle">
            Upload legal documents, ask questions about Indian law, and get
            accurate answers with source citations — powered by RAG and LLaMA.
          </p>

          <div className="hero-features">
            <div className="hero-feature">
              <span className="feature-icon">📚</span>
              <div>
                <strong>Cited Answers</strong>
                <p>Every response includes Act, Section, and quoted passage</p>
              </div>
            </div>
            <div className="hero-feature">
              <span className="feature-icon">📄</span>
              <div>
                <strong>Upload Your Documents</strong>
                <p>PDFs, images, and text files analyzed with AI</p>
              </div>
            </div>
            <div className="hero-feature">
              <span className="feature-icon">🛡</span>
              <div>
                <strong>No Hallucinations</strong>
                <p>Guardrailed to say "I don't know" instead of guessing</p>
              </div>
            </div>
          </div>

          <div className="hero-actions">
            <Link to="/dashboard" className="btn btn-primary btn-lg">
              Start Asking Questions →
            </Link>
            <Link to="/documents" className="btn btn-secondary btn-lg">
              Upload Documents
            </Link>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="landing-footer">
        <p>
          LexAI provides general legal information, not legal advice.
          Consult a qualified advocate for your specific situation.
        </p>
      </footer>
    </div>
  )
}
