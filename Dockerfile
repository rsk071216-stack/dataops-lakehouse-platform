# Pipeline image: the exact code CI tested, run by the Azure Container Apps Job.
# Base images are pinned by digest; Dependabot (docker ecosystem) proposes bumps.

FROM ghcr.io/astral-sh/uv:0.13.0@sha256:cdc6093146eb3ff6a40107b38f008b789e050e77ad87865e381d9917da55a168 AS uv

FROM python:3.14.7-slim-trixie@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS build
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /app

# Dependencies first (cached layer), strictly from the committed lockfile.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src ./src
COPY transform ./transform
COPY contracts ./contracts
COPY data ./data
RUN uv sync --frozen --no-dev

# Bake dbt packages and the manifest into the image (dagster-dbt loads it at start).
WORKDIR /app/transform
RUN DBT_PROFILES_DIR=. DBT_TARGET=postgres /opt/venv/bin/dbt deps \
 && DBT_PROFILES_DIR=. DBT_TARGET=postgres /opt/venv/bin/dbt parse \
 && rm -rf logs

FROM python:3.14.7-slim-trixie@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d AS runtime
LABEL org.opencontainers.image.title="dataops-lakehouse-platform" \
      org.opencontainers.image.description="dlt + dbt + Dagster lakehouse pipeline with Write-Audit-Publish" \
      org.opencontainers.image.licenses="MIT"

RUN groupadd --system --gid 10001 lakehouse \
 && useradd --system --uid 10001 --gid lakehouse --home-dir /app --no-create-home \
      --shell /usr/sbin/nologin lakehouse

COPY --from=build --chown=10001:10001 /opt/venv /opt/venv
COPY --from=build --chown=10001:10001 /app /app

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DAGSTER_HOME=/tmp/dagster \
    LAKEHOUSE_DLT_DIR=/tmp/dlt \
    DBT_SEND_ANONYMOUS_USAGE_STATS=false \
    DO_NOT_TRACK=1

USER 10001:10001
WORKDIR /app
# A batch job has no port to probe; Container Apps tracks the process exit code.
HEALTHCHECK NONE
ENTRYPOINT ["lakehouse"]
CMD ["run"]
