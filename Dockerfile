ARG NODE_IMAGE=node:20-alpine
ARG PYTHON_IMAGE=python:3.11-slim
ARG DEBIAN_MIRROR=https://deb.debian.org
ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_TRUSTED_HOST=

FROM ${NODE_IMAGE} AS frontend-build
WORKDIR /frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM ${PYTHON_IMAGE}
ARG DEBIAN_MIRROR
ARG PIP_INDEX_URL
ARG PIP_TRUSTED_HOST
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONIOENCODING=utf-8 \
    HF_HOME=/app/cache/huggingface
WORKDIR /app

RUN find /etc/apt -type f \( -name '*.list' -o -name '*.sources' \) \
      -exec sed -i \
        -e "s|https\?://deb.debian.org/debian-security|${DEBIAN_MIRROR}/debian-security|g" \
        -e "s|https\?://deb.debian.org/debian|${DEBIAN_MIRROR}/debian|g" {} + \
    && apt-get update \
    -o Acquire::Retries=3 \
    && apt-get install -y --no-install-recommends build-essential libjpeg62-turbo \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt ./requirements.txt
RUN if [ -n "${PIP_TRUSTED_HOST}" ]; then \
      pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" --trusted-host "${PIP_TRUSTED_HOST}" -r requirements.txt; \
    else \
      pip install --no-cache-dir --index-url "${PIP_INDEX_URL}" -r requirements.txt; \
    fi

COPY backend/ ./
COPY --from=frontend-build /frontend/dist ./frontend/dist
RUN mkdir -p /app/local-data /app/uploads /app/cache

EXPOSE 8088
HEALTHCHECK --interval=30s --timeout=5s --start-period=180s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/readyz', timeout=3).read()"
CMD ["python", "web_app.py", "--host", "0.0.0.0", "--port", "8088"]
