FROM archlinux:latest

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_CACHE_DIR=/root/.cache/uv \
    UV_LINK_MODE=copy \
    DOCKER_ENV=True \
    PATH="/opt/venv/bin:/usr/bin/vendor_perl:$PATH"


RUN pacman-key --init && \
    pacman-key --populate archlinux && \
    pacman -Syu --noconfirm base-devel uv rust perl-image-exiftool git nodejs pnpm && \
    rm -rf /var/cache/pacman/pkg/*

EXPOSE 8000
