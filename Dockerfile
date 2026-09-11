FROM python:3.12-slim

WORKDIR /app

# System deps required by mysql-connector-python's C extension
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc default-libmysqlclient-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 5000

# Production WSGI server. 2 workers x 4 threads = up to 8 concurrent requests;
# each worker imports wsgi:app and owns its own DB pool (pool_size=5), so this
# container holds ~10 MySQL connections.
CMD ["gunicorn", "--workers", "2", "--threads", "4", "--bind", "0.0.0.0:5000", "--timeout", "120", "wsgi:app"]
