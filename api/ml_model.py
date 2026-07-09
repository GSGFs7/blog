from abc import ABC, abstractmethod
from threading import Lock
from typing import TYPE_CHECKING, Any

from asgiref.sync import sync_to_async
from django.conf import settings

if TYPE_CHECKING:
    from httpx import AsyncClient, Client
    from sentence_transformers import SentenceTransformer

__all__ = [
    "EmbeddingProvider",
    "LocalEmbedding",
    "RemoteEmbedding",
    "get_ml_model",
]


class EmbeddingProvider(ABC):
    @abstractmethod
    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    @abstractmethod
    def embed_query(self, text: str) -> list[float]: ...
    @abstractmethod
    async def aembed_documents(self, texts: list[str]) -> list[list[float]]: ...
    @abstractmethod
    async def aembed_query(self, text: str) -> list[float]: ...

    @staticmethod
    def _validate_query_text(text: str):
        if not isinstance(text, str) or isinstance(text, list):
            raise TypeError("'text' must be a strings")

    @staticmethod
    def _validate_document_texts(texts: list[str]) -> None:
        if isinstance(texts, str) or not isinstance(texts, list):
            raise TypeError("'texts' must be a list of strings")


class LocalEmbedding(EmbeddingProvider):
    # class attribute
    _instance: "LocalEmbedding" = None
    _lock = Lock()

    # instance attribute
    model: SentenceTransformer

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                from sentence_transformers import SentenceTransformer

                cls._instance = super(LocalEmbedding, cls).__new__(cls, *args, **kwargs)
                # NOTE: this will block event loop in async. MUST warnup
                cls._instance.model = SentenceTransformer(
                    settings.MODEL_NAME,
                    cache_folder=settings.SENTENCE_TRANSFORMERS_HOME,
                    local_files_only=True,
                )

        return cls._instance

    def embed_query(self, text: str) -> list[float]:
        self._validate_query_text(text)
        embedding: Any = self.model.encode_query(text)
        return self._to_float_list(embedding)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self._validate_document_texts(texts)
        return [self._to_float_list(self.model.encode_document(text)) for text in texts]

    async def aembed_query(self, text: str) -> list[float]:
        return await sync_to_async(self.embed_query, thread_sensitive=False)(text)

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        return await sync_to_async(self.embed_documents, thread_sensitive=False)(texts)

    @staticmethod
    def _to_float_list(embedding: Any) -> list[float]:
        if hasattr(embedding, "tolist"):
            embedding = embedding.tolist()
        return [float(value) for value in embedding]


class RemoteEmbedding(EmbeddingProvider):
    _instance: "RemoteEmbedding" = None
    _lock = Lock()

    OPENAI_EMBEDDINGS_ENDPOINT = "/embeddings"

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(RemoteEmbedding, cls).__new__(
                    cls, *args, **kwargs
                )
            return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self.api_base = settings.REMOTE_EMBEDDING_API_BASE
        self.api_key = settings.REMOTE_EMBEDDING_API_KEY
        self.model_name = settings.REMOTE_EMBEDDING_MODEL_NAME
        self.client: Client | None = None
        self.aclient: AsyncClient | None = None

        # mark as inited
        self._initialized = True

    def embed_query(self, text: str) -> list[float]:
        self._validate_query_text(text)
        response = self._get_client().post(
            self.OPENAI_EMBEDDINGS_ENDPOINT,
            json={
                "input": text,
                "model": self.model_name,
            },
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        self._validate_document_texts(texts)
        response = self._get_client().post(
            self.OPENAI_EMBEDDINGS_ENDPOINT,
            json={
                "input": texts,
                "model": self.model_name,
            },
        )
        response.raise_for_status()
        data = response.json()["data"]
        return self._sort_result(data, len(texts))

    async def aembed_query(self, text: str) -> list[float]:
        self._validate_query_text(text)
        response = await self._get_aclient().post(
            self.OPENAI_EMBEDDINGS_ENDPOINT,
            json={
                "input": text,
                "model": self.model_name,
            },
        )
        response.raise_for_status()
        return response.json()["data"][0]["embedding"]

    async def aembed_documents(self, texts: list[str]) -> list[list[float]]:
        self._validate_document_texts(texts)
        response = await self._get_aclient().post(
            self.OPENAI_EMBEDDINGS_ENDPOINT,
            json={
                "input": texts,
                "model": self.model_name,
            },
        )
        response.raise_for_status()
        data = response.json()["data"]
        return self._sort_result(data, len(texts))

    @staticmethod
    def _sort_result(data, length):
        if len(data) != length:
            raise ValueError(
                f"Expected {length} embeddings, got {len(data)} from remote model"
            )

        # use None as a placeholder
        # noinspection PyTypeChecker
        embeddings: list[list[float]] = [None] * length
        for item in data:
            # OpenAI api endpoint has returns an index attribute
            embeddings[item["index"]] = item["embedding"]

        # verify
        if any(embedding is None for embedding in embeddings):
            raise ValueError("Remote model response is missing embedding indexes")

        return embeddings

    @property
    def _client_options(self) -> dict[str, Any]:
        return {
            "base_url": self.api_base,
            "headers": {"Authorization": f"Bearer {self.api_key}"},
            "timeout": 30.0,
        }

    def _get_client(self) -> Client:
        if self.client is None or self.client.is_closed:
            import httpx

            self.client: Client = httpx.Client(**self._client_options)
        # noinspection PyTypeChecker
        return self.client

    def _get_aclient(self) -> AsyncClient:
        if self.aclient is None or self.aclient.is_closed:
            import httpx

            self.aclient: AsyncClient = httpx.AsyncClient(**self._client_options)
        # noinspection PyTypeChecker
        return self.aclient


def get_ml_model() -> EmbeddingProvider:
    if settings.USE_REMOTE_EMBEDDING:
        return RemoteEmbedding()
    return LocalEmbedding()


if __name__ == "__main__":
    import os
    import sys

    import django
    import dotenv

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sys.path.append(project_root)
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "blog.settings")
    dotenv.load_dotenv()
    django.setup()

    print(RemoteEmbedding().embed_documents(["你好", "ciallo"]))
