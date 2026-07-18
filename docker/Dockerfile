FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# unprivileged runtime user; fixed uid/gid so the mounted data volume can be chowned to match
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid 10001 --create-home --home-dir /app app
WORKDIR /app
USER app

# build the venv as the app user so it isn't left root-owned
COPY --chown=app:app pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY --chown=app:app coach ./coach
COPY --chown=app:app examples ./examples

RUN mkdir -p /app/data  # a fresh coach_data volume inherits app ownership from here

EXPOSE 8000

CMD ["uvicorn", "--factory", "coach.backend.app:create_app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
