# A tela é construída numa etapa separada para que a imagem final não carregue
# Node nem node_modules — só o resultado do build.
FROM node:22-alpine AS web
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim AS runtime

# libgl e libglib são exigidas pelo OpenCV mesmo na variante headless.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 curl \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    OPENCV_OPENCL_RUNTIME=disabled \
    OPENCV_OPENCL_DEVICE=disabled

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ ./app/
COPY scripts/ ./scripts/
COPY data/ ./data/
COPY models/ ./models/
COPY --from=web /web/dist ./web/dist

# Uploads e banco de aprendizado ficam em volume: a imagem é descartável.
RUN mkdir -p var && useradd --create-home --uid 10001 tiss && chown -R tiss /app
USER tiss

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s \
    CMD curl -fsS http://127.0.0.1:8000/api/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
