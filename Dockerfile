FROM python:3.12-slim-bookworm

ARG VERSION=latest
ARG VCS_REF=unknown
ARG BUILD_DATE=

LABEL org.opencontainers.image.title="netzbremse-dashboard" \
    org.opencontainers.image.description="Streamlit dashboard for Netzbremse speedtest results" \
    org.opencontainers.image.url="https://github.com/lwndp/netzbremse-dashboard" \
    org.opencontainers.image.source="https://github.com/lwndp/netzbremse-dashboard" \
    org.opencontainers.image.version="${VERSION}" \
    org.opencontainers.image.revision="${VCS_REF}" \
    org.opencontainers.image.created="${BUILD_DATE}"

WORKDIR /app

# Install uv only (no curl/ca-certs bloat) — use system curl via APK equivalent
RUN apt-get update && \
    apt-get install -y --no-install-recommends curl ca-certificates && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    apt-get remove -y curl ca-certificates && \
    apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*

ENV PATH="/root/.local/bin:$PATH"

COPY pyproject.toml uv.lock ./

# Install only runtime deps (no dev), then remove uv to save space
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev && \
    rm -rf /root/.local/bin/uv

COPY . .

ENV DATA_DIR=/data
ENV REFRESH_INTERVAL_SECONDS=60

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD .venv/bin/python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=5)" || exit 1

ENTRYPOINT [".venv/bin/python", "-m", "streamlit", "run", "app/app.py", "--server.port=8501", "--server.address=0.0.0.0"]
