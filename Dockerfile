FROM python:3.11-slim

RUN apt-get update && apt-get install -y \
    adb \
    android-tools-adb \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN pip install --no-cache-dir uiautomator2 upnpclient fastapi uvicorn

COPY app.py .
COPY index.html .

EXPOSE 8833

CMD ["python", "app.py"]