# syntax=docker/dockerfile:1
# Backup image with PostgreSQL client tools and upload script

FROM ghcr.io/gsgfs7/pgvector-alpine:v0.8.7-pg19.0-avx512

USER root

RUN apk add --no-cache bash ca-certificates python3 py3-pip && \
    pip install --no-cache-dir --break-system-packages boto3 python-dotenv && \
    apk del py3-pip

WORKDIR /app

COPY scripts/upload.py /app/

ENV PYTHONUNBUFFERED=1

ENTRYPOINT []
CMD [ "pg_dump", "--version" ]
