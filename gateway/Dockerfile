FROM python:3.14-alpine

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
      UV_LINK_MODE=copy \
      PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# uv.lock общий на весь workspace (единая версия транзитивных зависимостей
# для всех модулей), но --package gateway ставит только его зависимости:
# не тянет elasticsearch/neo4j/psycopg/pymongo/faker, которые gateway
# не импортирует ни разу. --frozen не требует pyproject.toml остальных
# членов workspace на диске — доверяет уже посчитанному uv.lock.
COPY pyproject.toml uv.lock ./
COPY gateway/pyproject.toml ./gateway/pyproject.toml
RUN uv sync --frozen --package gateway --no-install-project

COPY gateway ./gateway

RUN adduser -D -u 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

CMD ["uvicorn", "gateway.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
