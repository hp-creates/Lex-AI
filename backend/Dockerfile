# ============================================================
# LexAI Backend — Multi-stage Docker Build
# Target: AWS EC2 t3.medium (4GB RAM, x86_64)
#
# Stage 1: Install Python dependencies with uv
# Stage 2: Slim runtime with only what's needed
# ============================================================

# --- Stage 1: Builder ---
FROM python:3.13-slim AS builder

# Install uv for fast dependency resolution
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /build

# Copy dependency files first (cache layer)
COPY pyproject.toml uv.lock* ./

# Install dependencies into a virtual environment
RUN uv venv /build/.venv && \
    uv sync --no-dev --frozen 2>/dev/null || uv sync --no-dev

# --- Stage 2: Runtime ---
FROM python:3.13-slim AS runtime

# System deps for PyMuPDF (PDF processing)
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        libmupdf-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy virtual environment from builder
COPY --from=builder /build/.venv /app/.venv

# Add venv to PATH
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH="/app"
ENV PYTHONUNBUFFERED=1

# Copy application code
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY data/ ./data/

# Create directories for runtime data
RUN mkdir -p /app/data/corpus /app/data/uploads

# Health check
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD curl -f http://localhost:8000/api/v1/health || exit 1

# Expose port
EXPOSE 8000

# Start uvicorn (single worker for t3.medium — Jina model is heavy)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
