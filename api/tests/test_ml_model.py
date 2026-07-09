import sys
from types import SimpleNamespace
from unittest.mock import patch

from asgiref.sync import async_to_sync
from django.test import SimpleTestCase, override_settings

from api.ml_model import LocalEmbedding, RemoteEmbedding, get_ml_model

# this test wrote by LLM


class VectorLike:
    def __init__(self, values):
        self.values = values

    def tolist(self):
        return self.values


class FakeSentenceTransformer:
    instances = []

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self.query_calls = []
        self.document_calls = []
        self.__class__.instances.append(self)

    def encode_query(self, text):
        self.query_calls.append(text)
        return VectorLike(["1.5", 2, 3.25])

    def encode_document(self, text):
        self.document_calls.append(text)
        return (len(text), "4.5")


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload
        self.raise_for_status_calls = 0

    def raise_for_status(self):
        self.raise_for_status_calls += 1

    def json(self):
        return self.payload


class FakeClient:
    is_closed = False

    def __init__(self, response):
        self.response = response
        self.posts = []

    def post(self, endpoint, json):
        self.posts.append((endpoint, json))
        return self.response


class FakeAsyncClient(FakeClient):
    async def post(self, endpoint, json):
        self.posts.append((endpoint, json))
        return self.response


class CreatedClient:
    instances = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.is_closed = False
        self.__class__.instances.append(self)


class CreatedAsyncClient(CreatedClient):
    instances = []


def _reset_all_singletons():
    LocalEmbedding._instance = None
    RemoteEmbedding._instance = None


def _patch_sentence_transformer():
    module = SimpleNamespace(SentenceTransformer=FakeSentenceTransformer)
    return patch.dict(sys.modules, {"sentence_transformers": module})


class _EmbeddingModelMixin:
    def test_rejects_invalid_input_shapes(self):
        model = self._make_model()
        for value in (["hello"], 1, None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    model.embed_query(value)
        for value in ("hello", ("hello",), None):
            with self.subTest(value=value):
                with self.assertRaises(TypeError):
                    model.embed_documents(value)

    def _make_model(self):
        raise NotImplementedError


class LocalEmbeddingTest(_EmbeddingModelMixin, SimpleTestCase):
    def setUp(self):
        _reset_all_singletons()
        FakeSentenceTransformer.instances = []
        self.module_patch = _patch_sentence_transformer()
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        self.addCleanup(_reset_all_singletons)

    def _make_model(self):
        return LocalEmbedding()

    @override_settings(
        MODEL_NAME="unit-test-model",
        SENTENCE_TRANSFORMERS_HOME="/tmp/sentence-transformers",
    )
    def test_initializes_sentence_transformer_once_from_settings(self):
        first = LocalEmbedding()
        second = LocalEmbedding()

        self.assertIs(first, second)
        self.assertEqual(len(FakeSentenceTransformer.instances), 1)
        transformer = FakeSentenceTransformer.instances[0]
        self.assertEqual(transformer.args, ("unit-test-model",))
        self.assertEqual(
            transformer.kwargs,
            {
                "cache_folder": "/tmp/sentence-transformers",
                "local_files_only": True,
            },
        )

    def test_embed_query_casts_vector_like_output_to_floats(self):
        model = LocalEmbedding()

        self.assertEqual(model.embed_query("hello"), [1.5, 2.0, 3.25])
        self.assertEqual(model.model.query_calls, ["hello"])

    def test_embed_documents_casts_each_document_to_floats(self):
        model = LocalEmbedding()

        self.assertEqual(
            model.embed_documents(["a", "bb"]),
            [[1.0, 4.5], [2.0, 4.5]],
        )
        self.assertEqual(model.model.document_calls, ["a", "bb"])

    def test_async_methods_return_embeddings(self):
        model = LocalEmbedding()

        self.assertEqual(async_to_sync(model.aembed_query)("hello"), [1.5, 2.0, 3.25])
        self.assertEqual(
            async_to_sync(model.aembed_documents)(["abc"]),
            [[3.0, 4.5]],
        )


@override_settings(
    REMOTE_EMBEDDING_API_BASE="https://embedding.example/v1",
    REMOTE_EMBEDDING_API_KEY="test-key",
    REMOTE_EMBEDDING_MODEL_NAME="test-embedding-model",
)
class RemoteEmbeddingTest(_EmbeddingModelMixin, SimpleTestCase):
    def setUp(self):
        _reset_all_singletons()
        self.addCleanup(_reset_all_singletons)

    def _make_model(self):
        return RemoteEmbedding()

    def test_initializes_once_from_settings(self):
        first = RemoteEmbedding()
        second = RemoteEmbedding()

        self.assertIs(first, second)
        self.assertEqual(first.api_base, "https://embedding.example/v1")
        self.assertEqual(first.api_key, "test-key")
        self.assertEqual(first.model_name, "test-embedding-model")

    def test_client_options_include_auth_and_timeout(self):
        model = RemoteEmbedding()

        self.assertEqual(
            model._client_options,
            {
                "base_url": "https://embedding.example/v1",
                "headers": {"Authorization": "Bearer test-key"},
                "timeout": 30.0,
            },
        )

    def test_embed_query_posts_openai_payload(self):
        model = RemoteEmbedding()
        response = FakeResponse({"data": [{"embedding": [0.25, 0.75]}]})
        model.client = FakeClient(response)

        self.assertEqual(model.embed_query("hello"), [0.25, 0.75])
        self.assertEqual(
            model.client.posts,
            [
                (
                    "/embeddings",
                    {"input": "hello", "model": "test-embedding-model"},
                )
            ],
        )
        self.assertEqual(response.raise_for_status_calls, 1)

    def test_embed_documents_posts_payload_and_sorts_by_index(self):
        model = RemoteEmbedding()
        response = FakeResponse(
            {
                "data": [
                    {"index": 1, "embedding": [2.0]},
                    {"index": 0, "embedding": [1.0]},
                ]
            }
        )
        model.client = FakeClient(response)

        self.assertEqual(model.embed_documents(["first", "second"]), [[1.0], [2.0]])
        self.assertEqual(
            model.client.posts,
            [
                (
                    "/embeddings",
                    {
                        "input": ["first", "second"],
                        "model": "test-embedding-model",
                    },
                )
            ],
        )
        self.assertEqual(response.raise_for_status_calls, 1)

    def test_async_methods_post_payloads_and_return_embeddings(self):
        model = RemoteEmbedding()
        query_response = FakeResponse({"data": [{"embedding": [0.5]}]})
        model.aclient = FakeAsyncClient(query_response)

        self.assertEqual(async_to_sync(model.aembed_query)("hello"), [0.5])
        self.assertEqual(query_response.raise_for_status_calls, 1)

        documents_response = FakeResponse(
            {
                "data": [
                    {"index": 1, "embedding": [20.0]},
                    {"index": 0, "embedding": [10.0]},
                ]
            }
        )
        model.aclient.response = documents_response

        self.assertEqual(
            async_to_sync(model.aembed_documents)(["first", "second"]),
            [[10.0], [20.0]],
        )
        self.assertEqual(
            model.aclient.posts,
            [
                (
                    "/embeddings",
                    {"input": "hello", "model": "test-embedding-model"},
                ),
                (
                    "/embeddings",
                    {
                        "input": ["first", "second"],
                        "model": "test-embedding-model",
                    },
                ),
            ],
        )
        self.assertEqual(documents_response.raise_for_status_calls, 1)

    def test_sort_result_rejects_bad_remote_payloads(self):
        with self.assertRaisesMessage(ValueError, "Expected 2 embeddings"):
            RemoteEmbedding._sort_result([{"index": 0, "embedding": [1.0]}], 2)

        with self.assertRaisesMessage(ValueError, "missing embedding indexes"):
            RemoteEmbedding._sort_result(
                [
                    {"index": 1, "embedding": [1.0]},
                    {"index": 1, "embedding": [2.0]},
                ],
                2,
            )

        self.assertEqual(RemoteEmbedding._sort_result([], 0), [])

    def test_get_client_builds_reuses_and_recreates_httpx_clients(self):
        CreatedClient.instances = []
        CreatedAsyncClient.instances = []
        httpx_module = SimpleNamespace(
            Client=CreatedClient,
            AsyncClient=CreatedAsyncClient,
        )

        with patch.dict(sys.modules, {"httpx": httpx_module}):
            model = RemoteEmbedding()

            client = model._get_client()
            self.assertIs(model._get_client(), client)
            self.assertEqual(client.kwargs, model._client_options)

            client.is_closed = True
            replacement = model._get_client()
            self.assertIsNot(replacement, client)
            self.assertEqual(len(CreatedClient.instances), 2)

            async_client = model._get_aclient()
            self.assertIs(model._get_aclient(), async_client)
            self.assertEqual(async_client.kwargs, model._client_options)

            async_client.is_closed = True
            async_replacement = model._get_aclient()
            self.assertIsNot(async_replacement, async_client)
            self.assertEqual(len(CreatedAsyncClient.instances), 2)


class GetMLModelTest(SimpleTestCase):
    def setUp(self):
        _reset_all_singletons()
        FakeSentenceTransformer.instances = []
        self.module_patch = _patch_sentence_transformer()
        self.module_patch.start()
        self.addCleanup(self.module_patch.stop)
        self.addCleanup(_reset_all_singletons)

    @override_settings(USE_REMOTE_EMBEDDING=True)
    def test_returns_remote_embedding_when_configured(self):
        self.assertIsInstance(get_ml_model(), RemoteEmbedding)

    @override_settings(
        USE_REMOTE_EMBEDDING=False,
        MODEL_NAME="unit-test-model",
        SENTENCE_TRANSFORMERS_HOME="/tmp/sentence-transformers",
    )
    def test_returns_local_embedding_by_default(self):
        self.assertIsInstance(get_ml_model(), LocalEmbedding)
