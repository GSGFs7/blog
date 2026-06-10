import asyncio
import logging
import typing
import uuid
from abc import ABC, abstractmethod

from django.core.cache import cache
from ninja.security import HttpBearer

from core.fernet import get_fernet

if typing.TYPE_CHECKING:
    from cryptography.fernet import MultiFernet

logger = logging.getLogger(__name__)


class TimeBaseAuth(HttpBearer, ABC):
    """
    S2S authentication based on Fernet. TTL: 30s

    token format: client_id:nonce
    """

    @classmethod
    def create_token(cls, client_id: str, nonce: str | None = None) -> str:
        if nonce is None:
            nonce = uuid.uuid4().hex

        f = cls.get_fernet()
        payload = cls.generate_token_format(client_id, nonce).encode("utf-8")
        return f.encrypt(payload).decode("utf-8")

    @staticmethod
    def generate_auth_token_cache_key(client_id: str, nonce: str) -> str:
        return f"auth_token:{client_id}:{nonce}"

    @staticmethod
    def generate_token_format(client_id: str, nonce: str):
        return f"{client_id}:{nonce}"

    @staticmethod
    def get_fernet() -> MultiFernet:
        return get_fernet()

    @abstractmethod
    def authenticate(self, request, token):
        raise NotImplementedError("use AsyncTimeBaseAuth or SyncTimeBaseAuth instead")


# TODO: Auth,
#  1. multi-client and corresponding API key verification
#  2. fine-grained permissions: read/write
class AsyncTimeBaseAuth(TimeBaseAuth):
    """
    Asynchronous S2S authentication based on Fernet. TTL: 30s
    """

    @classmethod
    async def authenticate(cls, request, token):
        try:
            # fernet decrypt
            f = cls.get_fernet()
            decrypt_token_bytes: bytes = await asyncio.to_thread(
                f.decrypt, token.encode(), ttl=30
            )
            decrypt_token = decrypt_token_bytes.decode()

            # get payload
            client_id, nonce = decrypt_token.split(":", 1)
            if not client_id or not nonce:
                return None

            cache_key = cls.generate_auth_token_cache_key(client_id, nonce)
            # TODO: Auth, cache storage DOS protection
            is_new_request = await cache.aadd(cache_key, 1, timeout=30)  # atomicity
            if not is_new_request:
                # protect against replay attacks
                return None

            return client_id
        except Exception as e:
            # ban attackers?
            logger.debug(e)
            return None


class SyncTimeBaseAuth(TimeBaseAuth):
    """
    Synchronous S2S authentication based on Fernet. TTL: 30s
    """

    @classmethod
    def authenticate(cls, request, token):
        try:
            f = cls.get_fernet()
            decrypt_token = f.decrypt(token.encode(), ttl=30).decode("utf-8")

            client_id, nonce = decrypt_token.split(":", 1)
            if not client_id or not nonce:
                return None

            cache_key = cls.generate_auth_token_cache_key(client_id, nonce)
            is_new_request = cache.add(cache_key, 1, timeout=30)
            if not is_new_request:
                return None

            return client_id
        except Exception as e:
            logger.debug(e)
            return None
