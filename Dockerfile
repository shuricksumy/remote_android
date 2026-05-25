# ==============================================================================
# STAGE 1: ISOLATED WEB BUILDER INTERFACES
# ==============================================================================
# Use the exact same base image to guarantee Node.js C++ binding compatibility
FROM python:3.11-alpine AS web-builder

# Install core native dependencies required to download and compile git assets
RUN apk add --no-cache git make g++ gcc musl-dev nodejs npm

WORKDIR /build

# Clone the repository, compile the dist folder, and strip out bulky dev tools
RUN git clone https://github.com/NetrisTV/ws-scrcpy.git . && \
    npm install && \
    npm run dist && \
    npm prune --production

# ==============================================================================
# STAGE 2: FINAL PRODUCTION PYTHON RUNTIME
# ==============================================================================
FROM python:3.11-alpine

# Install standard system automation assets (ADB, Node, and video rendering libs)
# Notice we DO NOT install make or gcc here, keeping the image ultra-light!
RUN apk add --no-cache \
    android-tools \
    nodejs \
    npm \
    ffmpeg \
    mesa-gl \
    libusb \
    scrcpy

# Copy the completely compiled project safely to /opt (bypassing npm install entirely)
COPY --from=web-builder /build /opt/ws-scrcpy

# Create a clean, direct execution wrapper link that doesn't trigger C++ rebuilds
RUN echo '#!/bin/sh' > /usr/local/bin/ws-scrcpy && \
    echo 'node /opt/ws-scrcpy/dist/index.js "$@"' >> /usr/local/bin/ws-scrcpy && \
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