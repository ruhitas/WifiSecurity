# Wireless IDS + AI Platform — service image (Phase 14).
# One image runs any pipeline service, selected by $WIDS_SERVICE.
FROM python:3.11-slim

# MSSQL ODBC driver (for pyodbc against a networked SQL Server)
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg unixodbc unixodbc-dev ca-certificates && \
    curl -fsSL https://packages.microsoft.com/keys/microsoft.asc | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/microsoft-prod.gpg] https://packages.microsoft.com/debian/12/prod bookworm main" > /etc/apt/sources.list.d/mssql-release.list && \
    apt-get update && ACCEPT_EULA=Y apt-get install -y msodbcsql18 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt requirements-capture.txt ./
RUN pip install --no-cache-dir -r requirements.txt -r requirements-capture.txt

COPY src/ ./src/
COPY scripts/ ./scripts/
ENV PYTHONPATH=/app/src
ENV WIDS_SERVICE=feature-extractor

# Deep-learning extras (torch/tf) are installed only in the inference image
# variant via: docker build --build-arg WITH_ML=1 (see requirements-ml.txt).
ARG WITH_ML=0
COPY requirements-ml.txt ./
RUN if [ "$WITH_ML" = "1" ]; then pip install --no-cache-dir -r requirements-ml.txt; fi

ENTRYPOINT ["python", "scripts/service.py"]
