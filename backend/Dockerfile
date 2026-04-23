FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY app/ app/

# Expose port (Railway sets PORT env var)
EXPOSE 8000

# Run with uvicorn — use shell form so $PORT is expanded
CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
