FROM python:3.11-slim

# Install gosu and other utilities
RUN apt-get update && apt-get install -y --no-install-recommends \
    gosu \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ensure entrypoint is executable
RUN chmod +x /app/entrypoint.sh

# Ensure data directories exist
RUN mkdir -p /app/wiki /app/sources /app/snapshots /app/archive /app/schema /app/workspaces

EXPOSE 8300

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8300"]
