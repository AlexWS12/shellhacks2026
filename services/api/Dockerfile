FROM ghcr.io/astral-sh/uv:python3.14-bookworm-slim
WORKDIR /app
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1
COPY pyproject.toml uv.lock .python-version ./
COPY packages/core ./packages/core
COPY services ./services
RUN uv sync --frozen --no-dev --package tandem-api
EXPOSE 8000
CMD ["uv", "run", "--no-sync", "uvicorn", "tandem_api.main:app", "--host", "0.0.0.0", "--port", "8000"]
