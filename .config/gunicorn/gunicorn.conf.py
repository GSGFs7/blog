# gunicorn.conf.py

import os

from prometheus_client.multiprocess import mark_process_dead


def is_k8s_env() -> bool:
    return os.environ.get("K8S_ENV", "False").lower() in ("1", "true", "yes")


# Port
bind = "0.0.0.0:8000"

# Workers and threads
workers = 2 if is_k8s_env() else 4
worker_class = "core.worker.BoundedUvicornWorker"
graceful_timeout = 60

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


# exit hook
def child_exit(server, worker):
    if os.environ.get("PROMETHEUS_MULTIPROC_DIR"):
        mark_process_dead(worker.pid)
