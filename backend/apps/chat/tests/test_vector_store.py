"""Vector store factory tests."""

from django.test import SimpleTestCase, override_settings

from apps.chat.services.vector_store import (
    get_vector_store,
    is_azure_search_configured,
    use_azure_search,
    embedding_dimensions,
)


class VectorStoreFactoryTests(SimpleTestCase):
    @override_settings(AZURE_SEARCH_RAG_ENABLED=False)
    def test_defaults_to_chroma(self):
        store = get_vector_store()
        self.assertEqual(store.backend_name(), "chroma")

    @override_settings(
        AZURE_SEARCH_RAG_ENABLED=True,
        AZURE_SEARCH_ENDPOINT="https://test.search.windows.net",
        AZURE_SEARCH_KEY="key",
        AZURE_SEARCH_INDEX_NAME="test-index",
    )
    def test_uses_azure_when_enabled(self):
        self.assertTrue(use_azure_search())
        store = get_vector_store()
        self.assertEqual(store.backend_name(), "azure_search")

    def test_embedding_dimensions(self):
        self.assertEqual(embedding_dimensions("text-embedding-3-small"), 1536)
        self.assertEqual(embedding_dimensions("text-embedding-3-large"), 3072)

    @override_settings(AZURE_SEARCH_ENDPOINT="", AZURE_SEARCH_KEY="")
    def test_azure_not_configured_without_credentials(self):
        self.assertFalse(is_azure_search_configured())
