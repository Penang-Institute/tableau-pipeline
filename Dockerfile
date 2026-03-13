FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy pipeline code and config
COPY pipeline/ pipeline/
COPY opendosm.tsv .
COPY output/ output/

# Default: run all transforms
ENTRYPOINT ["python", "-m", "pipeline.orchestrator"]
