FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    OMR_SERVICE_HOST=0.0.0.0 \
    OMR_SERVICE_PORT=8080 \
    OMR_SERVICE_WORKERS=auto \
    OMR_SERVICE_DATA_DIR=/app/service_data \
    OMR_TEMPLATE_DIR=/app/inputs

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
        libgomp1 \
        libsm6 \
        libxext6 \
        libxrender1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/service_data /app/inputs /app/config

EXPOSE 8080

CMD ["python", "web/robyn_app.py"]
