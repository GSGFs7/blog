import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet, MultiFernet
from django.conf import settings


@lru_cache(maxsize=32)
def build_fernet(secret: str) -> Fernet:
    derived = hashlib.sha256(secret.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def get_fernet(key: str | None = None) -> MultiFernet:
    if key:
        return MultiFernet([build_fernet(key)])

    current = settings.FERNET_KEY or settings.API_KEY
    if not current:
        raise ValueError("FERNET_KEY or API_KEY is required for Fernet encryption")

    old_keys = settings.FERNET_OLD_KEYS
    fernets = [build_fernet(current)]
    fernets.extend(build_fernet(old_key) for old_key in old_keys if old_key)
    return MultiFernet(fernets)
