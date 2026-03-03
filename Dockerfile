# HIVE Agent Framework - Railway Deployment
FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    git \
    curl \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install uv package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh
ENV PATH="/root/.cargo/bin:$PATH"

# Set working directory
WORKDIR /app

# Clone HIVE repository
RUN git clone https://github.com/aden-hive/hive.git .

# Install dependencies using uv
RUN uv sync

# Create necessary directories
RUN mkdir -p /app/exports \
    && mkdir -p /app/.hive/credentials \
    && mkdir -p /app/data

# Expose port for HTTP API (if running as service)
EXPOSE 8000

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV HIVE_DATA_DIR=/app/data
ENV HIVE_CREDENTIALS_DIR=/app/.hive/credentials

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import framework; print('OK')" || exit 1

# Default command - run TUI dashboard
CMD ["uv", "run", "hive", "tui"]
