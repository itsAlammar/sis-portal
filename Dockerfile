FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# The SQLite file lives in /data so it can be mounted as a volume and
# survives container replacement. Back it up with:
#   docker exec <container> python manage.py backup
ENV SIS_DB_DIR=/data
RUN mkdir -p /data
VOLUME /data

EXPOSE 8000
CMD ["gunicorn", "--workers", "2", "--bind", "0.0.0.0:8000", "wsgi:app"]
