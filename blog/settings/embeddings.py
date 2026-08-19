import os

from .env import get_bool, get_str

# vector search
MODEL_NAME = get_str("MODEL_NAME")
SENTENCE_TRANSFORMERS_HOME = get_str("SENTENCE_TRANSFORMERS_HOME")

# LiteLLM
REMOTE_EMBEDDING_API_BASE = get_str(
    "REMOTE_EMBEDDING_API_BASE", "http://blog-litellm:4000/v1"
)
REMOTE_EMBEDDING_API_KEY = get_str("REMOTE_EMBEDDING_API_KEY", "sk-1234")
REMOTE_EMBEDDING_MODEL_NAME = get_str(
    "REMOTE_EMBEDDING_MODEL_NAME", "embeddinggemma-300m"
)
USE_REMOTE_EMBEDDING = get_bool("USE_REMOTE_EMBEDDING", False)

# supervisord may use root permissions
# PermissionError: [Errno 13] Permission denied: '/root/.cache/huggingface/token'
if SENTENCE_TRANSFORMERS_HOME:
    os.environ["HF_HOME"] = SENTENCE_TRANSFORMERS_HOME
    # 'local_files_only=True'
    # This setting only prevents the download of model weights.
    # But 'transformers' or 'huggingface_hub' may still attempt to connect to network
    os.environ["HF_HUB_OFFLINE"] = "1"

# Disable hugging face process bar
os.environ["HF_HUB_DISABLE_PROGRESS_BARS"] = "1"
