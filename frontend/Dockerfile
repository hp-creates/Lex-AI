# ============================================================
# LexAI Frontend — Multi-stage Docker Build
# Stage 1: Build Vite React app
# Stage 2: Serve with nginx
# ============================================================

# --- Stage 1: Builder ---
FROM node:22-alpine AS builder

WORKDIR /build

# Copy package files first (cache layer)
COPY package.json package-lock.json* ./

RUN npm ci

# Copy source and build
COPY . .

# Build args become VITE_ env vars at build time
ARG VITE_SUPABASE_URL
ARG VITE_SUPABASE_ANON_KEY
ARG VITE_API_BASE_URL=/api/v1

RUN npm run build

# --- Stage 2: Serve with nginx ---
FROM nginx:alpine AS runtime

# Remove default nginx page
RUN rm -rf /usr/share/nginx/html/*

# Copy built assets
COPY --from=builder /build/dist /usr/share/nginx/html

# Copy custom nginx config
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
