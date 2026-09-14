# Spark

Spark is a self-hosted electricity-consumption tracker built with FastAPI,
SQLite, HTMX, and ECharts. Technical documentation is available in
[`docs/`](docs/README.md).

## Install with Docker Compose

### Requirements

- Docker Engine
- Docker Compose v2

Clone the repository and create the environment file:

```console
git clone https://github.com/CSharplie/spark.git
cd spark
cp .env.example .env
```

Generate a secret, then set the resulting value as `SPARK_SECRET_KEY` in
`.env`:

```console
openssl rand -hex 32
```

Pull the published image from GitHub Container Registry and start Spark:

```console
docker compose pull
docker compose up -d
docker compose ps
```

The default image is `ghcr.io/csharplie/spark:latest`. Set `SPARK_IMAGE` in
`.env` to pin a release tag or digest. If the package is private, authenticate
with a GitHub token that has `read:packages` permission before pulling:

```console
echo "$CR_PAT" | docker login ghcr.io -u USERNAME --password-stdin
```

Create the first account:

```console
docker compose exec app spark-cli create-user
```

Open <http://localhost:8000> and sign in with that account. Application data is
stored in the `spark-data` Docker volume and survives container upgrades.

### Upgrade

```console
docker compose pull
docker compose up -d
docker image prune -f
```

Database migrations run automatically when the container starts.

## Local development

### Requirements

- Python 3.13
- `uv`

Install the locked dependencies and prepare the environment:

```console
uv sync --locked
cp .env.example .env
uv run alembic upgrade head
uv run spark-cli create-user
```

Start the development server:

```console
uv run spark
```

The application is available at <http://localhost:8000>. Run the checks with:

```console
uv run ruff check .
uv run ruff format --check .
uv run pytest
```

## Configuration

| Variable | Default | Description |
|---|---|---|
| `SPARK_IMAGE` | `ghcr.io/csharplie/spark:latest` | Container image used by Compose |
| `SPARK_ENV` | `development` | Runtime mode; use `production` behind HTTPS |
| `SPARK_SECRET_KEY` | development value | JWT signing secret; replace for every deployment |
| `SPARK_DATABASE_PATH` | `data/spark.db` | SQLite database path |
| `SPARK_JWT_EXPIRE_MINUTES` | `10080` | Session lifetime in minutes |
| `SPARK_CO2_FACTOR_G_PER_KWH` | `52.0` | CO2 conversion factor |
