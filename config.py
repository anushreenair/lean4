"""Configuration for the Lean documentation loader."""

from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlparse


@dataclass(frozen=True)
class Config:
    base_url: str = os.getenv(
        "LEAN_DOCS_BASE_URL", "https://lean-lang.org/doc/reference/latest/"
    )
    cache_path: Path = Path(os.getenv("LEAN_DOCS_CACHE", ".lean-doc-cache.json"))
    timeout: float = float(os.getenv("LEAN_DOCS_TIMEOUT", "12"))
    max_pages: int = int(os.getenv("LEAN_DOCS_MAX_PAGES", "80"))

    @property
    def allowed_host(self) -> str:
        return self.base_url.split("/", 3)[2].lower()

    @property
    def allowed_path_prefix(self) -> str:
        path = urlparse(self.base_url).path.rstrip("/")
        return path or "/"
