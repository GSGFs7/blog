import logging

from cryptography.fernet import InvalidToken
from django.db import models

from core.fernet import get_fernet

logger = logging.getLogger(__name__)


class DecryptionError(Exception):
    pass


class FernetField(models.TextField):
    """Fernet transparent encryption"""

    def __init__(self, *args, fernet_key=None, **kwargs):
        self.fernet_key = fernet_key
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.fernet_key is not None:
            kwargs["fernet_key"] = self.fernet_key
        return name, path, args, kwargs

    def _field_label(self) -> str:
        if self.model is not None:
            return f"{self.model.__qualname__}.{self.attname}"
        return self.attname or "unknown"

    def get_prep_value(self, value: str):
        if value is None or value == "":
            return value

        try:
            f = get_fernet(self.fernet_key)
            return f.encrypt(value.encode()).decode()
        except Exception as e:
            raise ValueError(f"Encryption failed on {self._field_label()}: {e}") from e

    def from_db_value(self, value: str, expression, connection):
        if value is None or value == "":
            return value

        try:
            f = get_fernet(self.fernet_key)
            return f.decrypt(value.encode()).decode()
        except InvalidToken:
            label = self._field_label()
            logger.error(
                "Decryption failed on %s (wrong key or corrupted ciphertext)", label
            )
            raise DecryptionError(
                f"Cannot decrypt {label}: key mismatch or corrupted data."
            )
        except Exception as e:
            label = self._field_label()
            raise DecryptionError(f"Decryption error on {label}: {e}") from e

    def value_from_object(self, obj):
        return getattr(obj, self.attname)
