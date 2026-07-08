# gunicorn.conf.py

import os


def is_k8s_env() -> bool:
    return os.environ.get("K8S_ENV", "False").lower() in ("1", "true", "yes")


# Port
bind = "0.0.0.0:8000"

# Workers and threads
workers = 2 if is_k8s_env() else 4
worker_class = "uvicorn.workers.UvicornWorker"

# Logging
accesslog = "-"
errorlog = "-"
loglevel = (
    "debug" if (os.environ.get("DEBUG", "false") in ("1", "true", "yes")) else "info"
)
capture_output = True

daemon = False

# prevent memory leaks
# destroy it if a worker processed 10k request
max_requests = 10000
max_requests_jitter = 1000

worker_kwargs = {
    # replicas * workers * limit_concurrency <= PGBOUNCER_MAX_CLIENT_CONN * 0.7
    "limit_concurrency": 160,
}
