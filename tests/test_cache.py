from pathlib import Path

import pytest

from config import Config
from docs_loader import DocumentationCrawler, DocumentationUnavailable, JsonDocumentCache
from docs_index import Document


def test_cache_reuses_documents_without_fetching(tmp_path: Path):
    cache = JsonDocumentCache(tmp_path / "docs.json")
    docs = [Document("Title", "https://lean-lang.org/a", ("Heading",), "body")]
    cache.save(docs)

    assert cache.load() == docs


def test_missing_cache_is_explicit(tmp_path: Path):
    cache = JsonDocumentCache(tmp_path / "missing.json")

    with pytest.raises(DocumentationUnavailable):
        cache.require_documents()


def test_crawler_repeated_load_uses_cache(tmp_path: Path):
    cache = JsonDocumentCache(tmp_path / "docs.json")
    docs = [Document("Title", "https://lean-lang.org/a", ("Heading",), "body")]
    cache.save(docs)
    crawler = DocumentationCrawler(Config(cache_path=cache.path), cache)
    crawler._crawl = lambda: pytest.fail("network crawl should not run for a cached query")

    assert crawler.load() == docs
