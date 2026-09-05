FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    OUTPUT_DIR=/data

RUN apt-get update \
    && apt-get install --no-install-recommends -y fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/* \
    && addgroup --system app \
    && adduser --system --ingroup app --home /app app

WORKDIR /app
COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir . \
    && mkdir -p /data \
    && chown -R app:app /data

USER app
VOLUME ["/data"]

HEALTHCHECK --interval=1m --timeout=5s --start-period=6m --retries=3 \
  CMD python -m app.healthcheck

CMD ["python", "-m", "app.worker"]
