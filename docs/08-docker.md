# Container deployment

The production image is published to GitHub Container Registry as
`ghcr.io/csharplie/spark` by `.github/workflows/docker-publish.yml`
(tags: `latest` and the branch name on pushes to `main`, the tag name on
`v*` tags).

## Image

- Multi-stage build (`Dockerfile`): dependencies installed with
  `uv sync --locked --no-dev`, runtime on `python:3.13-slim-bookworm`.
- Runs as the unprivileged user `spark` (UID 10001), listens on port
  **8000**.
- On start: `alembic upgrade head`, then Uvicorn (`app.main:app`, one
  process).
- SQLite database in `/app/data` (a volume).
- Healthcheck: `GET /healthz` every 30 s (timeout 3 s, start period
  10 s, 3 retries). It checks that the app answers, not the database.
- Needs outbound HTTPS to `geocoding-api.open-meteo.com` and
  `archive-api.open-meteo.com` for the temperature features.

## Compose

`compose.yaml` runs a single `app` service:

| Variable | Value in the container |
|---|---|
| `SPARK_ENV` | always `production` (Secure cookies, HSTS, API docs disabled) |
| `SPARK_DATABASE_PATH` | always `/app/data/spark.db` |
| `SPARK_SECRET_KEY` | from `.env`, **required** (Compose refuses to start if unset or empty) |
| `SPARK_JWT_EXPIRE_MINUTES` | from `.env`, default `10080` |
| `SPARK_CO2_FACTOR_G_PER_KWH` | from `.env`, default `52.0` |
| `SPARK_IMAGE` | from `.env`, default `ghcr.io/csharplie/spark:latest` (image to run) |

The database lives in the `spark-data` named volume (Docker prefixes it
with the Compose project name, e.g. `spark_spark-data`).

Compose doesn't check the secret's strength: the placeholder from
`.env.example` must be replaced.

## Start the application

Create the local environment file and generate a secret:

```console
cp .env.example .env
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set the generated value as `SPARK_SECRET_KEY` in `.env`, then pull and start
Spark:

```console
docker compose pull
docker compose up -d
docker compose ps
```

The application is available at <http://localhost:8000>. Set `SPARK_IMAGE` in
`.env` to select a release tag or immutable digest.

Because the container runs in production mode, session cookies are
`Secure`: browsers accept them on `http://localhost`, but any other access
must go through a reverse proxy that terminates TLS (HTTPS).

Private packages require authentication with a GitHub token that has
`read:packages` permission:

```console
echo "$CR_PAT" | docker login ghcr.io -u USERNAME --password-stdin
```

## Create the first account

Account creation remains CLI-only (see [04-auth.md](./04-auth.md)):

```console
docker compose exec app spark-cli create-user
```

If the terminal reports invalid UTF-8 input, retry and type the password
manually instead of pasting it. Spark reports this condition without printing a
traceback.

## Operations

```console
# Follow application logs
docker compose logs -f app

# Pull and deploy a new image (migrations run automatically)
docker compose pull
docker compose up -d

# Stop the container while retaining data
docker compose down
```

Stop writes before copying the SQLite database from the named volume:

```console
mkdir -p backups
docker compose stop app
docker run --rm --volumes-from "$(docker compose ps -aq app)" \
  -v "$PWD/backups:/backup" alpine cp /app/data/spark.db /backup/spark.db
docker compose start app
```

Remove the persistent data only when explicitly required:

```console
docker compose down --volumes
```