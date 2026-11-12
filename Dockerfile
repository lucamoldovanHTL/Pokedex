FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Statische Dateien zur Build-Zeit sammeln (Key nur für diesen Schritt)
RUN DJANGO_DEBUG=0 DJANGO_SECRET_KEY=build-only-not-secret python manage.py collectstatic --noinput \
    && chmod +x docker/entrypoint.sh \
    && useradd --create-home --uid 1000 app && chown -R app /app
USER app

EXPOSE 8000
ENTRYPOINT ["docker/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--threads", "4", "--access-logfile", "-"]
