# syntax=docker/dockerfile:1
FROM archlinux:latest

WORKDIR /app

# Unified environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DOCKER_ENV="True" \
    PATH="/app/.venv/bin:/usr/bin/vendor_perl:$PATH"

# Install system dependencies and create user
RUN pacman-key --init && \
    pacman-key --populate archlinux && \
    pacman -Syu --noconfirm base-devel uv perl-image-exiftool git nodejs pnpm && \
    rm -rf /etc/pacman.d/gnupg/ /var/cache/pacman/pkg/ && \
    useradd -m -u 1000 user && \
    chown user /app

USER user

# Pre-install Python and frontend dependencies
COPY --chown=user:user pyproject.toml uv.lock package.json pnpm-lock.yaml /app/
COPY --chown=user:user scripts/copy-katex.mjs /app/scripts/
RUN uv sync --frozen --no-install-project --no-cache && \
    pnpm install --frozen-lockfile

# Copy project files, build frontend, and collect static
COPY --chown=user:user . .
RUN pnpm run build:all && \
    uv run manage.py collectstatic --noinput && \
    rm -rf /app/node_modules
