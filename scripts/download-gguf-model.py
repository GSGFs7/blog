# this file is used by k3s GGUF model download


import logging
import os

from filelock import FileLock
from huggingface_hub import snapshot_download

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

if __name__ == "__main__":
    GGUF_MODEL_NAME = os.environ.get("GGUF_MODEL_NAME")
    if GGUF_MODEL_NAME is None:
        raise ValueError("GGUF_MODEL_NAME environment variable is not set.")

    SENTENCE_TRANSFORMERS_HOME = os.environ.get("SENTENCE_TRANSFORMERS_HOME")
    if SENTENCE_TRANSFORMERS_HOME is None:
        raise ValueError("SENTENCE_TRANSFORMERS_HOME environment variable is not set.")

    HUGGINGFACE_HUB_TOKEN = os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if HUGGINGFACE_HUB_TOKEN is None:
        raise ValueError("HUGGINGFACE_HUB_TOKEN environment variable is not set.")
    HUGGINGFACE_HUB_TOKEN = HUGGINGFACE_HUB_TOKEN.strip()

    os.makedirs(SENTENCE_TRANSFORMERS_HOME, exist_ok=True)

    lock_id = f"{GGUF_MODEL_NAME or ''}".replace("/", "_")
    lock_file = os.path.join(SENTENCE_TRANSFORMERS_HOME, f"{lock_id}.lock")
    lock = FileLock(lock_file)

    logger.info("Acquiring lock for model downloading...")

    with lock:
        logger.info(f"Starting download of GGUF model: {GGUF_MODEL_NAME}")
        local_dir = os.path.join(
            SENTENCE_TRANSFORMERS_HOME, GGUF_MODEL_NAME.replace("/", "--")
        )
        snapshot_download(
            repo_id=GGUF_MODEL_NAME,
            local_dir=local_dir,
            token=HUGGINGFACE_HUB_TOKEN,
        )
        logger.info(f"GGUF Model {GGUF_MODEL_NAME} is ready at {local_dir}")
