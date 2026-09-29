FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
# gunicorn is a production-only server and cannot run on Windows (the local dev
# environment), so it is installed here rather than pinned in requirements.txt.
RUN pip install --no-cache-dir -r requirements.txt gunicorn

COPY . .

EXPOSE 5000

# Served on 5000 inside the container; the compose file maps host 5010 -> 5000.
CMD ["gunicorn", "--workers", "2", "--threads", "4", "--bind", "0.0.0.0:5000", "app:app"]
