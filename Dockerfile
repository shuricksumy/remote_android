# ==============================================================================
# STAGE 1: ISOLATED WEB BUILDER INTERFACES
# ==============================================================================
FROM node:20-alpine AS web-builder

# Install core native dependencies required to download and compile git assets
RUN apk add --no-cache git python3 make g++ gcc musl-dev

WORKDIR /build

# Clone the official repository and compile the distribution bundle locally
RUN git clone https://github.com/NetrisTV/ws-scrcpy.git . && \
    npm install && \
    npm run dist && \
    cd dist && \
    npm install --omit=dev

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

# Copy over compiled distribution folder directly from the builder stage
COPY --from=web-builder /build/dist /usr/local/lib/node_modules/ws-scrcpy

# 🚀 FIX: Enforce permissions and create a safe shell wrapper execution binary link
RUN chmod +x /usr/local/lib/node_modules/ws-scrcpy/index.js && \
    echo '#!/bin/sh' > /usr/local/bin/ws-scrcpy && \
    echo 'node /usr/local/lib/node_modules/ws-scrcpy/index.js "$@"' >> /usr/local/bin/ws-scrcpy && \
    chmod +x /usr/local/bin/ws-scrcpy

WORKDIR /app

# Install your Python FastAPI framework requirements directly inline
RUN pip install --no-cache-dir fastapi uvicorn uiautomator2 upnpclient

# Copy over your core web application logic scripts
COPY app.py index.html .

# Expose your standard control interfaces (8833 and 8834 run on host mode anyway)
EXPOSE 8833 8834

# Fire up your Python orchestrator daemon
CMD ["python", "app.py"]