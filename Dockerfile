# ==============================================================================
# STAGE 1: ISOLATED WEB BUILDER INTERFACES
# ==============================================================================
# Use Node 18 LTS to guarantee compatibility with ws-scrcpy's native C++ modules
FROM node:18-alpine AS web-builder

RUN apk add --no-cache git python3 make g++ gcc musl-dev

WORKDIR /build

# Clone the repository, compile the dist folder, and strip out bulky dev tools
RUN git clone https://github.com/NetrisTV/ws-scrcpy.git . && \
    npm install && \
    npm run dist && \
    npm prune --production

# ==============================================================================
# STAGE 2: FINAL PRODUCTION PYTHON RUNTIME
# ==============================================================================
# Must use the exact same Node 18 base image so the compiled C++ binaries match the engine!
FROM node:18-alpine

# Install Python, ADB, scrcpy, and required system tools directly via apk
RUN apk add --no-cache \
    python3 \
    py3-pip \
    android-tools \
    ffmpeg \
    mesa-gl \
    libusb \
    scrcpy

# Copy the perfectly compiled project from Stage 1 safely to /opt
COPY --from=web-builder /build /opt/ws-scrcpy

# Create a clean, direct execution wrapper link for ws-scrcpy
RUN echo '#!/bin/sh' > /usr/local/bin/ws-scrcpy && \
    echo 'node /opt/ws-scrcpy/dist/index.js "$@"' >> /usr/local/bin/ws-scrcpy && \
    chmod +x /usr/local/bin/ws-scrcpy

WORKDIR /app

# Allow pip to install global packages safely inside the Alpine container
ENV PIP_BREAK_SYSTEM_PACKAGES=1

# Install your Python FastAPI framework requirements
RUN pip3 install --no-cache-dir fastapi uvicorn uiautomator2 upnpclient

# Copy over your core web application logic scripts
COPY app.py index.html config.yaml .

# Expose your standard control interfaces (8833 for FastAPI, 8834 for Video Socket)
EXPOSE 8833 8834

# Fire up your Python orchestrator daemon (using python3 command explicitly)
CMD ["python3", "app.py"]
