FROM python:3.14-alpine

# uv не входит в образ python — берём готовый бинарник.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# Отдельный слой: пересобирается только при изменении зависимостей.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY lab1 ./lab1

RUN adduser -D -u 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8000/healthcheck >/dev/null || exit 1

CMD ["uvicorn", "lab1.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
