# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    DJANGO_SETTINGS_MODULE=config.settings.production

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      build-essential \
      libpango-1.0-0 \
      libpangoft2-1.0-0 \
      libcairo2 \
      libjpeg62-turbo \
      libffi-dev \
      libxml2-dev \
      libxslt1-dev \
      zlib1g-dev \
 && rm -rf /var/lib/apt/lists/*

COPY requirements/base.txt /app/requirements/base.txt
RUN pip install --upgrade pip \
 && pip install -r /app/requirements/base.txt \
 && pip install "gunicorn==23.0.0" "whitenoise==6.8.2"

RUN groupadd -r django && useradd -r -g django django \
 && mkdir -p /app/staticfiles /app/media /app/data \
 && chown -R django:django /app

COPY --chown=django:django entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

COPY --chown=django:django . /app/

EXPOSE 8000

USER django

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--access-logfile", "-", "--error-logfile", "-"]