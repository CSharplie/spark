# Container deployment

The production image is published to GitHub Container Registry as
`ghcr.io/csharplie/spark`. Docker Compose persists the SQLite database in the
`spark-data` named volume. The container applies Alembic migrations before
starting Uvicorn and runs as an unprivileged user.

## Start the application

Create the local environment file and replace the secret with a random value:

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

The application is available at <http://localhost:8000>. Compose rejects an
unset secret instead of starting production with the development default.
Set `SPARK_IMAGE` in `.env` to select a release tag or immutable digest.

Private packages require authentication with a GitHub token that has
`read:packages` permission:

```console
echo "$CR_PAT" | docker login ghcr.io -u USERNAME --password-stdin
```

## Create the first account

Account creation remains CLI-only:

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