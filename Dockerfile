FROM node:22-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
WORKDIR /app

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ ./backend/
COPY config/ ./config/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

ENV NETMAP_CONFIG=/app/config/netmap.yaml

EXPOSE 8585

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8585", "--app-dir", "/app/backend"]
