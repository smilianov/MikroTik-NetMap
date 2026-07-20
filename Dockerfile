# Base images are pinned to specific patch versions — bump deliberately.
FROM node:22.23.1-alpine AS frontend-build
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13.14-slim
WORKDIR /app

# Install libcap2-bin (for setcap) and create a dedicated non-root runtime
# user with a fixed UID/GID so host volume ownership can be matched
# (see docs/INSTALLATION.md).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libcap2-bin \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 netmap \
    && useradd --uid 10001 --gid netmap --home-dir /app --shell /usr/sbin/nologin netmap

COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# Grant the Python interpreter cap_net_raw so the privileged ICMP ping
# monitor (icmplib) works without running as root, then remove setcap again.
RUN setcap 'cap_net_raw+ep' "$(readlink -f "$(command -v python)")" \
    && apt-get purge -y libcap2-bin \
    && rm -rf /var/lib/apt/lists/*

COPY --chown=netmap:netmap backend/ ./backend/
COPY --chown=netmap:netmap config/ ./config/
COPY --from=frontend-build --chown=netmap:netmap /app/frontend/dist ./frontend/dist

ENV NETMAP_CONFIG=/app/config/netmap.yaml

EXPOSE 8585

USER netmap

# python:slim has no curl — probe the health endpoint with urllib instead.
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8585/api/health', timeout=4)"]

CMD ["python", "-m", "uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8585", "--app-dir", "/app/backend"]
