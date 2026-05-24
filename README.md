docker build -t uapp-automation-api:latest .
docker compose up -d --build
curl -X POST http://127.0.0.1:8833/trigger