FROM python:3.13-slim

WORKDIR /app

# System deps for curl (healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# Copy project metadata (for pip install)
COPY pyproject.toml /tmp/pyproject.toml

# Install Python dependencies from pyproject.toml
RUN pip install --no-cache-dir $(python -c "
import tomllib, pathlib
data = tomllib.loads(pathlib.Path('/tmp/pyproject.toml').read_text())
print(' '.join(f'\"{d}\"' for d in data['project']['dependencies']))
")

# Copy backend code
COPY backend/ .

ENV PYTHONPATH=/app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
