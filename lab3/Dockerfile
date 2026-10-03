FROM python:3.14-alpine

# uv не входит в образ python — берём готовый бинарник.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

# uv.lock общий на весь workspace, но --package lab3 ставит только его
# зависимости: не тянет pwdlib/pyjwt/python-multipart/faker/pymongo,
# которые lab3 не импортирует. --frozen не требует pyproject.toml
# остальных членов workspace на диске.
COPY pyproject.toml uv.lock ./
COPY lab3/pyproject.toml ./lab3/pyproject.toml
RUN uv sync --frozen --package lab3 --no-install-project

COPY lab3 ./lab3

RUN adduser -D -u 1000 app && chown -R app:app /app
USER app

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD wget -qO- http://127.0.0.1:8000/healthcheck >/dev/null || exit 1

CMD ["uvicorn", "lab3.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
