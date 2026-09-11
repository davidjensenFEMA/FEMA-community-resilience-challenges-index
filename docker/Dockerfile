# Production Dockerfile for FEMA CRIA
# Minimal image with only production dependencies

FROM python:3.11-slim

# Metadata
LABEL maintainer="John Hutchison"
LABEL description="FEMA CRIA Production Environment"
LABEL version="2.0.0"

# Install system dependencies (minimal set)
RUN apt-get update && apt-get install -y \
    gcc \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Poetry
ENV POETRY_VERSION=1.7.1
ENV POETRY_HOME=/opt/poetry
ENV POETRY_NO_INTERACTION=1
ENV POETRY_VIRTUALENVS_IN_PROJECT=false
ENV POETRY_VIRTUALENVS_CREATE=false

RUN pip install poetry==${POETRY_VERSION}

# Set working directory
WORKDIR /app

# Copy dependency files
COPY pyproject.toml poetry.lock ./

# Install ONLY production dependencies
RUN poetry install --no-dev --no-root --no-interaction --no-ansi

# Copy application code
COPY . .

# Install the project
RUN poetry install --no-dev --no-interaction --no-ansi

# Create necessary directories
RUN mkdir -p /app/data /app/output /app/logs

# Set Python path
ENV PYTHONPATH=/app

# Run migrations and start application
# (This can be overridden with docker-compose or docker run)
CMD ["python", "-m", "scripts.run_county_workflow"]
