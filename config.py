"""Configuration for the Lean documentation loader."""

from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlparse


@dataclass(frozen=True)
class Config:
    # Environment variables make the crawler configurable without changing source code.
    base_url: str = os.getenv(
        "LEAN_DOCS_BASE_URL", "https://lean-lang.org/doc/reference/latest/"
    )
    cache_path: Path = Path(os.getenv("LEAN_DOCS_CACHE", ".lean-doc-cache.json"))
    timeout: float = float(os.getenv("LEAN_DOCS_TIMEOUT", "12"))
    max_pages: int = int(os.getenv("LEAN_DOCS_MAX_PAGES", "80"))

    @property
    def allowed_host(self) -> str:
        # Restricting the host prevents the crawler from leaving official Lean documentation.
        return self.base_url.split("/", 3)[2].lower()

    @property
    def allowed_path_prefix(self) -> str:
        # Restricting the path keeps linked pages inside the configured reference section.
        path = urlparse(self.base_url).path.rstrip("/")
        return path or "/"
