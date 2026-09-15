FROM python:3.14-alpine

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
      UV_LINK_MODE=copy \
      PATH="/app/.venv/bin:$PATH"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project

COPY /gateway ./gateway

RUN uv sync --frozen

CMD ["uv", "run", "uvicorn", "gateway.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]