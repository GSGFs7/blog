import logging
import os

from celery import Celery
from celery.signals import worker_process_init

logger = logging.getLogger(__name__)


def is_k8s_env() -> bool:
    """Check if running in Kubernetes environment"""
    return os.environ.get("K8S_ENV", "False").lower() in ("1", "true", "yes")


# needs this to run `celery -A blog worker -l info` command
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "blog.settings")

app = Celery("blog")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.conf.update(worker_concurrency=1 if is_k8s_env() else 2)
app.autodiscover_tasks()  # discover tasks for django


@worker_process_init.connect
def preload_ml_model(sender, **kwargs):
    """
    Preload ML model in each worker process when it starts to avoid first task timeout.
    """
    logger.info("Worker process initializing, preloading ML model...")
    try:
        # Import inside signal handler to avoid loading model when importing celery.py
        from api.ml_model import get_ml_model

        model = get_ml_model()
        if model:
            logger.info("ML model preloaded successfully.")
        else:
            logger.warning("ML model preloaded failed.")
    except Exception as e:
        logger.warning(f"ML model preload failed: {e}")
