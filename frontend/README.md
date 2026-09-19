# LexAI Frontend

Single-page web client for LexAI built with React 18 and Vite. It provides an interactive conversational workspace, legal document upload and OCR inspection, and multi-session chat persistence.

For the project overview, visit the [Main Documentation](../README.md). For detailed benchmarks and latency evaluations, see the [Engineering Case Study](../CASE_STUDY.md). For backend API endpoints, see the [Backend Documentation](../backend/README.md).

---

## Core Capabilities

- **Interactive Legal Chat Workspace**:
  - Conversational interface with multi-turn context.
  - Markdown rendering with support for structured tables, statutory quotes, bulleted legal checklists, and code blocks.
  - Interactive statutory citation pills that link to relevant legal sections.
  - Visual status badges indicating when responses are augmented via web search fallback.
- **Document Scoping and Analysis**:
  - Drag-and-drop file upload supporting legal notices, agreements, and FIRs in PDF and image formats.
  - Chat-scoped context: allows users to query uploaded documents in isolated chat sessions without cross-conversation context bleeding.
- **Authentication and Session Persistence**:
  - Google OAuth and email-based authentication via Supabase Auth.
  - Claude-style session sidebar: restores past conversations, allows session renaming, and supports cascading deletion.
- **Design System**:
  - Responsive Vanilla CSS architecture with custom design tokens.
  - Dark-mode optimized without external CSS framework overhead.

---

## Technical Stack

- **Framework**: React 18
- **Tooling & Bundler**: Vite
- **Routing**: React Router DOM (v6)
- **Database & Auth Client**: `@supabase/supabase-js`
- **Markdown Rendering**: `react-markdown` with `remark-gfm`
- **Iconography**: `lucide-react`
- **API Client**: Native fetch with centralized response parsing in `src/lib/api.js`

---

## Directory Structure

```text
frontend/
|-- public/                # Static public assets
|-- src/
|   |-- assets/            # Vector graphics and icons
|   |-- components/        # Reusable UI components
|   |   |-- MessageBubble.jsx   # Message bubble with markdown table support
|   |   |-- MessageBubble.css   # Message styles, table styles, citation badges
|   |   |-- Navbar.jsx          # Top navigation bar and auth actions
|   |   `-- ...
|   |-- pages/             # View pages
|   |   |-- Landing.jsx         # Landing page and platform introduction
|   |   |-- Dashboard.jsx       # Chat interface, sessions sidebar, and document picker
|   |   |-- Dashboard.css       # Layout styles for dashboard workspace
|   |   `-- Documents.jsx       # Document repository and upload interface
|   |-- lib/               # Shared client modules
|   |   |-- api.js              # REST client for FastAPI backend
|   |   `-- supabase.js         # Supabase client instantiation
|   |-- App.jsx            # Application routing setup
|   |-- main.jsx           # React DOM root initialization
|   `-- index.css          # Design tokens, typography, and global resets
|-- index.html             # HTML entry point
|-- package.json           # Node dependencies and scripts
`-- vite.config.js         # Vite configuration
```

---

## Local Development

### 1. Prerequisites

- Node.js 20 or higher
- npm or pnpm package manager

### 2. Installation

Navigate to the `frontend/` directory and install dependencies:

```powershell
cd frontend
npm install
```

### 3. Environment Configuration

Create a `.env` file in the `frontend/` directory:

```ini
# Backend API Base URL
VITE_API_BASE_URL=http://localhost:8000

# Supabase Auth and Database
VITE_SUPABASE_URL=https://your-supabase-project.supabase.co
VITE_SUPABASE_ANON_KEY=your-supabase-anon-key
```

### 4. Run Development Server

```powershell
npm run dev
```

The application will be accessible at `http://localhost:5173`.

---

## Production Build

To compile static assets for production:

```powershell
npm run build
```

The compiled output will be generated in the `dist/` directory.

To preview the build locally:

```powershell
npm run preview
```
