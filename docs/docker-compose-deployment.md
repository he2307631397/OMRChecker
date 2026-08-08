# Docker Compose Deployment

This deployment starts the Robyn OMR API with CPU-only PaddleOCR support on port `8088`.

## Files

- `Dockerfile`: builds the Python 3.12 service image and installs CPU-only OCR dependencies.
- `docker-compose.yml`: runs the Robyn API service, exposes port `8088`, and mounts persistent data directories.
- `.env.docker.example`: environment template for Docker Compose.

## CPU-only OCR dependencies

The image pins the OCR runtime to:

- `paddlepaddle==3.2.0`
- `paddleocr==3.7.0`

The Dockerfile does not install CUDA, cuDNN, or NVIDIA runtime packages.

## First-time setup

From the repository root:

```bash
cp .env.docker.example .env.docker
mkdir -p service_data outputs inputs config
```

For production COS batch recognition, create `config/robyn-service.json` from `config/robyn-service.example.json` and fill in the real COS bucket, region, callback URL, and credentials. The compose file mounts `./config` read-only into the container, so changes on the host are visible after restarting the service.

For local mock-COS mode, set `"cos": { "enabled": false, ... }` in `config/robyn-service.json` or omit the file and use the service defaults.

## Start the service

```bash
docker compose up -d --build
```

The API listens at:

```text
http://localhost:8088
```

Health check:

```bash
curl http://localhost:8088/health
```

Expected response includes:

```json
{
  "status": "ok",
  "service": "omrchecker-robyn",
  "workers": 1,
  "template_dir": "/app/inputs"
}
```

## Runtime data

The compose deployment persists runtime data on the host:

- `./service_data` -> `/app/service_data`
- `./outputs` -> `/app/outputs`
- `./inputs` -> `/app/inputs` read-only
- `./config` -> `/app/config` read-only

`service_data` stores the SQLite task database, COS mock files, per-sheet working data, and service artifacts. `outputs` stores normal OMRChecker outputs when the pipeline writes to the configured output root.

## Useful commands

Validate compose syntax:

```bash
docker compose config
```

Watch logs:

```bash
docker compose logs -f omr-api
```

Restart after config changes:

```bash
docker compose restart omr-api
```

Stop the service:

```bash
docker compose down
```

## Notes

- The service port is configured through `OMR_SERVICE_PORT=8088` and compose maps `8088:8088`.
- Compose sets `OMR_SERVICE_HOST=0.0.0.0` so Robyn accepts traffic forwarded from the host.
- The API recognition path is the same `run_omr_directory -> entry/process_dir` pipeline used by CLI and regression tests.
- Keep `.env.docker` and `config/robyn-service.json` uncommitted because they may contain credentials.
