# =============================================================================
# SILC Docker Image - Multi-stage build
# =============================================================================
# This creates a containerized SILC daemon with web UI.
#
# Build:
#   docker build -t silc:latest .
#
# Run:
#   docker run -d --name silc -p 19999:19999 -p 20000-20010:20000-20010 silc:latest
#
# Access:
#   Manager UI: http://localhost:19999/
#   Session UI: http://localhost:20000/web
#   REST API:   http://localhost:20000/status
# =============================================================================

# -----------------------------------------------------------------------------
# Stage 1: Build the web UI
# -----------------------------------------------------------------------------
FROM node:20-alpine AS web-builder

WORKDIR /app

# Copy web UI source (vite outputs to ../static/manager)
COPY manager_web_ui/package*.json ./manager_web_ui/
WORKDIR /app/manager_web_ui
RUN npm install --prefer-offline

# Copy the rest and build
COPY manager_web_ui/ ./
RUN npm run build

# Output is now at /app/static/manager

# -----------------------------------------------------------------------------
# Stage 2: Python runtime with SILC
# -----------------------------------------------------------------------------
FROM python:3.12-slim

WORKDIR /app

# Install system dependencies for PTY support
RUN apt-get update && apt-get install -y --no-install-recommends \
    procps \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies first (better caching)
COPY pyproject.toml ./
RUN pip install --no-cache-dir hatchling && \
    pip install --no-cache-dir --no-deps fastapi uvicorn[standard] click psutil requests platformdirs websockets httpx toml aiofiles textual par-term-emu-core-rust mcp

# Copy the SILC package source
COPY silc/ ./silc/

# Copy the built web UI from stage 1
COPY --from=web-builder /app/static/manager ./static/manager

# Create data directory for persistence
RUN mkdir -p /root/.silc/logs

# Expose ports
# 19999 = Daemon manager API + Web UI
# 20000-21000 = Session ports (default range)
EXPOSE 19999 20000-21000

# Environment defaults
ENV SILC_DAEMON_PORT=19999
ENV SILC_PORT_RANGE=20000-21000

# Start the daemon (runs in foreground inside container)
CMD ["python", "-m", "silc", "daemon"]
