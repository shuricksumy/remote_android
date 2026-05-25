# ==============================================================================
# STAGE 1: ISOLATED WEB BUILDER INTERFACES
# ==============================================================================
FROM node:20-alpine AS web-builder

# Install core native dependencies required to compile node-gyp assets
RUN apk add --no-cache git python3 make g++ gcc musl-dev

WORKDIR /build
# Pull and install ws-scrcpy tools globally inside the isolated cache stage
RUN npm install -g ws-scrcpy --unsafe-perm

# ==============================================================================
# STAGE 2: FINAL PRODUCTION PYTHON RUNTIME
# ==============================================================================
FROM python:3.11-alpine

# Install standard system automation assets (ADB, Node, and video rendering libs)
RUN apk add --no-cache \
    android-tools \
    nodejs \
    npm \
    ffmpeg \
    mesa-gl \
    libusb

# Copy over compiled global node modules directly from the builder stage
COPY --from=web-builder /usr/local/lib/node_modules /usr/local/lib/node_modules
COPY --from=web-builder /usr/local/bin/ws-scrcpy /usr/local/bin/ws-scrcpy

WORKDIR /app

# Install your Python FastAPI dependencies separately to maximize layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy over your core web application logic scripts
COPY app.py index.html .

# Expose your ports: 8833 (FastAPI Core) and 8000 (ws-scrcpy stream socket)
EXPOSE 8833 8000

# Fire up your Python orchestrator daemon
CMD ["python", "app.py"]