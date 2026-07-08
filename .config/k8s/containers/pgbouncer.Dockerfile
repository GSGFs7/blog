FROM archlinux:latest

# pgbouncer user exist yet
RUN pacman -Syu --noconfirm ca-certificates pgbouncer postgresql

COPY .config/pgbouncer/entrypoint.sh /usr/local/bin/pgbouncer-entrypoint

RUN chmod +x /usr/local/bin/pgbouncer-entrypoint

USER pgbouncer

ENTRYPOINT ["pgbouncer-entrypoint"]
