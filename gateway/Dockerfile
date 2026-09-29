# Multi-stage production Dockerfile for SES Semantic Engine Gateway
# Stage 1: Build dependencies in a temporary container
FROM python:3.12-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libssl-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Instalar Rust Toolchain (Requerido por Maturin/PyO3 para compilar jas_vector_core)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

COPY pyproject.toml README.md ./
COPY core_rs/ ./core_rs/
COPY ses/ ./ses/
COPY gateway/ ./gateway/

RUN pip install --no-cache-dir --upgrade pip maturin && \
    pip install --no-cache-dir ".[server]"

# Stage 2: Minimal, secure runtime container
FROM python:3.12-slim AS runner

WORKDIR /app

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app

# Create non-root unprivileged service user
RUN groupadd -g 10001 sesgroup && \
    useradd -u 10001 -g sesgroup -s /sbin/nologin -m sesuser

# Copy virtual environment from builder
COPY --from=builder /opt/venv /opt/venv

# Copy application source files
COPY --chown=sesuser:sesgroup ses/ ./ses/
COPY --chown=sesuser:sesgroup gateway/ ./gateway/
COPY --chown=sesuser:sesgroup pyproject.toml README.md ./

USER sesuser

EXPOSE 8000

# Native Python healthcheck (zero external binaries needed)
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; sys_exit = 0 if urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=3).getcode() == 200 else 1; exit(sys_exit)"

CMD ["uvicorn", "gateway.server:app", "--host", "0.0.0.0", "--port", "8000"]
