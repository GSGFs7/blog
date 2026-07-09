# syntax=docker/dockerfile:1
# Backup image with PostgreSQL client tools and upload script

FROM archlinux:latest

# Install PostgreSQL client
RUN pacman-key --init && \
    pacman-key --populate archlinux && \
    pacman -Syu --noconfirm postgresql python-pip && \
    rm -rf /etc/pacman.d/gnupg/ /var/cache/pacman/pkg/

# Create working directory
WORKDIR /app

# Copy upload script
COPY scripts/upload.py /app/

# Install Python dependencies (from pypi)
# Using --break-system-packages because Arch Linux is an externally managed environment
RUN pip install --no-cache-dir boto3 boto3-stubs[s3] python-dotenv --break-system-packages

ENV PYTHONUNBUFFERED=1

# Set default command
CMD ["pg_dump", "--version"]
