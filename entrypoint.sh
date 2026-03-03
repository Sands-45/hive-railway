#!/bin/bash
set -e

# Get port from environment or default to 8000
PORT=${PORT:-8000}

echo "Starting HIVE API server on port $PORT..."

# Run uvicorn with the correct port
exec python -m uvicorn server:app --host 0.0.0.0 --port "$PORT"
