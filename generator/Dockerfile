FROM python:3.14-alpine

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# uv.lock общий на весь workspace, но --package generator ставит только его
# зависимости: не тянет fastapi/uvicorn/httpx/pwdlib/pyjwt — generator не
# сервер, у него нет ни одной строки с их импортом. --frozen не требует
# pyproject.toml остальных членов workspace на диске.
COPY pyproject.toml uv.lock ./
COPY generator/pyproject.toml ./generator/pyproject.toml
RUN uv sync --frozen --package generator --no-install-project

COPY generator ./generator

RUN adduser -D -u 1000 app && chown -R app:app /app
USER app

# Одноразовая задача, не сервер. ENTRYPOINT позволяет передавать
# команду аргументом: docker compose run --rm generator generate
ENTRYPOINT ["python", "-m", "generator.main"]
CMD ["generate"]
