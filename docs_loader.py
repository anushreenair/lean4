"""Official-domain documentation crawler and JSON cache."""

from html.parser import HTMLParser
import json
from pathlib import Path
from urllib.parse import urljoin, urldefrag, urlparse
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from config import Config
from docs_index import Document


class DocumentationUnavailable(RuntimeError):
    # A dedicated error lets the CLI explain offline/cache failures without a traceback.
    pass


class _PageParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.headings: list[str] = []
        self.parts: list[str] = []
        self.links: list[str] = []
        self._current: list[str] = []
        self._capture_title = False
        self._heading_level: int | None = None
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag in {"script", "style", "nav", "footer"}:
            # These sections are navigation or implementation noise, not reference content.
            self._skip += 1
        if tag == "a" and attrs_dict.get("href"):
            self.links.append(attrs_dict["href"])
        if tag == "title":
            self._capture_title = True
        if tag in {"h1", "h2", "h3"}:
            self._heading_level = int(tag[1])

    def handle_endtag(self, tag):
        if tag in {"script", "style", "nav", "footer"}:
            self._skip = max(0, self._skip - 1)
        if tag == "title":
            self._capture_title = False
        if tag in {"h1", "h2", "h3"}:
            value = " ".join(self._current).strip()
            if value:
                self.headings.append(value)
            self._current = []
            self._heading_level = None

    def handle_data(self, data):
        if self._skip:
            return
        value = " ".join(data.split())
        if not value:
            return
        if self._capture_title:
            self.title += value + " "
        if self._heading_level:
            self._current.append(value)
        self.parts.append(value)

    def document(self, url: str) -> Document:
        title = self.title.strip() or (self.headings[0] if self.headings else url)
        return Document(title, url, tuple(self.headings), " ".join(self.parts))


class JsonDocumentCache:
    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> list[Document]:
        # Cache reuse makes normal runs quick and allows operation without network access.
        if not self.path.exists():
            return []
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            return [Document.from_json(item) for item in payload.get("documents", [])]
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise DocumentationUnavailable(f"Could not read documentation cache: {exc}") from exc

    def require_documents(self) -> list[Document]:
        documents = self.load()
        if not documents:
            raise DocumentationUnavailable(f"No cached documentation at {self.path}")
        return documents

    def save(self, documents: list[Document]) -> None:
        # JSON keeps the cache human-readable and uses only the standard library.
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"documents": [document.to_json() for document in documents]}
        self.path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


class DocumentationCrawler:
    def __init__(self, config: Config, cache: JsonDocumentCache):
        self.config = config
        self.cache = cache

    def load(self, refresh: bool = False) -> list[Document]:
        # Refresh is explicit so a normal question never performs an unnecessary crawl.
        if not refresh:
            cached = self.cache.load()
            if cached:
                return cached
        try:
            documents = self._crawl()
        except Exception as exc:
            # A previous cache is safer than failing completely when the network is unavailable.
            cached = self.cache.load()
            if cached:
                return cached
            raise DocumentationUnavailable(f"Official documentation unavailable: {exc}") from exc
        self.cache.save(documents)
        return documents

    def _crawl(self) -> list[Document]:
        # Breadth-first crawling follows documentation links while honoring the page limit.
        base = self._canonical(self.config.base_url)
        queue = [base]
        seen: set[str] = set()
        documents: list[Document] = []
        while queue and len(documents) < self.config.max_pages:
            url = queue.pop(0)
            if url in seen or not self._allowed(url):
                continue
            seen.add(url)
            parser = _PageParser()
            request = Request(url, headers={"User-Agent": "lean-documentation-first-agent/1.0"})
            try:
                with urlopen(request, timeout=self.config.timeout) as response:
                    parser.feed(response.read().decode("utf-8", errors="replace"))
            except (HTTPError, URLError, TimeoutError):
                # One stale link must not discard otherwise usable documentation.
                # The outer load() still reports a clear error if the crawl found nothing.
                continue
            document = parser.document(url)
            if document.text:
                documents.append(document)
            for href in parser.links:
                next_url = self._canonical(urljoin(url, href))
                if self._allowed(next_url) and next_url not in seen:
                    queue.append(next_url)
        if not documents:
            raise DocumentationUnavailable("No readable official documentation pages found")
        return documents

    def _allowed(self, url: str) -> bool:
        # Host and path checks prevent unrelated websites from entering the documentation index.
        parsed = urlparse(url)
        path = parsed.path.rstrip("/") or "/"
        prefix = self.config.allowed_path_prefix
        return (
            parsed.scheme in {"http", "https"}
            and parsed.netloc.lower() == self.config.allowed_host
            and (path == prefix or path.startswith(prefix + "/"))
        )

    @staticmethod
    def _canonical(url: str) -> str:
        # Preserve a directory's trailing slash so relative documentation links
        # resolve beneath the configured reference root.
        return urldefrag(url)[0]
