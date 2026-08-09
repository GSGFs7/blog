# syntax=docker/dockerfile:1
# Unified Dockerfile
FROM archlinux:latest

ARG BUILD_ID=local
ENV APP_BUILD_ID=${BUILD_ID}

WORKDIR /app

# Unified environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DOCKER_ENV="True" \
    PATH="/app/.venv/bin:/usr/bin/vendor_perl:$PATH"

# Build arguments for model configuration
ARG MODEL_NAME
ARG SENTENCE_TRANSFORMERS_HOME
ENV MODEL_NAME=${MODEL_NAME}
ENV SENTENCE_TRANSFORMERS_HOME=${SENTENCE_TRANSFORMERS_HOME}

# Install system dependencies
RUN pacman-key --init && \
    pacman-key --populate archlinux && \
    pacman -Syu --noconfirm base-devel uv perl-image-exiftool git supervisor nodejs pnpm && \
    useradd -m -u 1000 user && \
    chown user /app

# Pre-install Python and frontend dependencies
COPY --chown=user:user pyproject.toml uv.lock package.json pnpm-lock.yaml /app/
COPY --chown=user:user native/crc64nvme /app/native/crc64nvme
COPY --chown=user:user native/markdown /app/native/markdown
COPY --chown=user:user scripts/copy-katex.mjs /app/scripts/
RUN uv sync --frozen --no-dev --extra ml --no-install-project --no-cache && \
    pnpm install --frozen-lockfile

# Copy download script first to enable early model download (better caching)
COPY --chown=user:user scripts/download-model.py /app/scripts/

# Download model using build secrets
RUN --mount=type=secret,id=hf_token \
    if [ -f /run/secrets/hf_token ]; then \
        export HUGGINGFACE_HUB_TOKEN=$(cat /run/secrets/hf_token); \
    fi && \
    uv run /app/scripts/download-model.py

# Copy the rest of the application
COPY --chown=user:user . .

# supervisor configuration
COPY --chown=root:root .config/supervisor/supervisord.conf /etc/supervisor/supervisord.conf

# prepare environment
RUN mkdir -p /var/log/supervisor && \
    chown -R user /var/log/supervisor && \
    pnpm run build:all && \
    uv run manage.py collectstatic --noinput

EXPOSE 8000

# supervisor needs to run as root to manage processes (it drops privileges for programs as per supervisord.conf)
CMD [ "supervisord" , "-c", "/etc/supervisor/supervisord.conf" ]
