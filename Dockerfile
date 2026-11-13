FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_ENV=production \
    HOST=0.0.0.0

WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app.py domain.py migrations.py pix.py run.py schema.sql ./
COPY templates/ ./templates/
COPY static/ ./static/

CMD ["python", "run.py"]
