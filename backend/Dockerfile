# Wine Shelf Scanner API
# Cloud Run optimized Dockerfile

FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create non-root user and ensure data directory exists (for GCS download)
RUN useradd -m -u 1000 appuser \
    && mkdir -p /app/app/data \
    && chown -R appuser:appuser /app
USER appuser

# Cloud Run uses PORT environment variable
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8080

# Startup: download DB from GCS -> run migrations -> start uvicorn
CMD ["python", "scripts/startup.py"]
