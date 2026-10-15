FROM ghcr.io/astral-sh/uv:0.13.1 AS uv
FROM python:3.14.8-slim-bookworm

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml uv.lock .python-version README.md LICENSE ./
COPY src ./src
COPY tests ./tests
COPY docs ./docs
RUN uv sync --locked --no-editable

CMD ["python", "-m", "pytest", "-q"]
