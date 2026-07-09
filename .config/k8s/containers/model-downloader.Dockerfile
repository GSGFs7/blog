FROM archlinux:latest

WORKDIR /app

ENV PATH="/app/.venv/bin:$PATH"

RUN pacman-key --init && \
    pacman-key --populate archlinux && \
    pacman -Syu --noconfirm python uv && \
    rm -rf /etc/pacman.d/gnupg/ /var/cache/pacman/pkg/ && \
    useradd -m -u 1000 user && \
    chown user:user /app

USER user

COPY --chown=user:user pyproject.toml uv.lock ./
RUN uv sync \
    --frozen \
    --only-group model-download \
    --no-install-project \
    --no-cache

COPY --chown=user:user scripts/download-gguf-model.py /app/scripts/

ENTRYPOINT ["python", "/app/scripts/download-gguf-model.py"]
