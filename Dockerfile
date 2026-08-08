FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1 \
    OMR_SERVICE_PORT=8088 \
    OMR_SERVICE_HOST=0.0.0.0 \
    OMR_SERVICE_DATA_DIR=/app/service_data \
    OMR_TEMPLATE_DIR=/app/inputs

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        fonts-noto-cjk \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        libsm6 \
        libxext6 \
        libxrender1 \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt \
    && python -m pip install paddlepaddle==3.2.0 paddleocr==3.7.0

COPY . .

RUN mkdir -p /app/service_data /app/outputs /app/inputs \
    && python - <<'PY'
import paddle
import paddleocr
print('paddle', paddle.__version__)
print('paddleocr', getattr(paddleocr, '__version__', 'unknown'))
PY

EXPOSE 8088

HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsS http://127.0.0.1:${OMR_SERVICE_PORT}/health || exit 1

CMD ["python", "web/robyn_app.py"]
