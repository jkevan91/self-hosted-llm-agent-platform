FROM python:3.11-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
        ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY thermalctl_server.py .

# Non-root. /secrets is mounted read-only (SSH key, hosts.yaml, known_hosts);
# /data holds the fan-curve change history.
RUN useradd -m -u 1000 mcpuser \
    && mkdir -p /data /secrets \
    && chown -R mcpuser:mcpuser /app /data
USER mcpuser

CMD ["python", "thermalctl_server.py"]
