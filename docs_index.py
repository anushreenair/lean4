"""A small deterministic local search index for cached documentation pages."""

from dataclasses import asdict, dataclass
import re
from typing import Iterable


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]*")


def tokenize(value: str) -> list[str]:
    # Lowercase word tokens give deterministic matching without a database or search service.
    return [token.lower() for token in TOKEN_RE.findall(value)]


@dataclass(frozen=True)
class Document:
    # A compact page record is enough for caching, searching, and source display.
    title: str
    url: str
    headings: tuple[str, ...]
    text: str

    def to_json(self) -> dict:
        return asdict(self)

    @classmethod
    def from_json(cls, value: dict) -> "Document":
        return cls(
            title=value["title"],
            url=value["url"],
            headings=tuple(value.get("headings", ())),
            text=value.get("text", ""),
        )


@dataclass(frozen=True)
class SearchResult:
    # Search results retain the query and source fields needed for explainable answers.
    query: str
    title: str
    url: str
    section: str
    text: str
    score: float

    def to_json(self) -> dict:
        return asdict(self)


class DocumentIndex:
    def __init__(self, documents: Iterable[Document]):
        self.documents = tuple(documents)

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        # A small local index keeps searches fast and reproducible in tests and offline runs.
        query_tokens = set(tokenize(query))
        if not query_tokens:
            return []
        scored: list[SearchResult] = []
        for document in self.documents:
            title_tokens = set(tokenize(document.title))
            heading_tokens = set(tokenize(" ".join(document.headings)))
            body_tokens = set(tokenize(document.text))
            title_hits = len(query_tokens & title_tokens)
            heading_hits = len(query_tokens & heading_tokens)
            body_hits = len(query_tokens & body_tokens)
            if not (title_hits or heading_hits or body_hits):
                continue
            # Titles and headings are stronger signals than a random body-text match.
            score = (4 * title_hits + 2 * heading_hits + body_hits) / len(query_tokens)
            section = document.headings[0] if document.headings else document.title
            scored.append(
                SearchResult(
                    query=query,
                    title=document.title,
                    url=document.url,
                    section=section,
                    text=_excerpt(document.text, query_tokens),
                    score=round(score, 4),
                )
            )
        return sorted(scored, key=lambda result: (-result.score, result.title))[:top_k]


def _excerpt(text: str, query_tokens: set[str], width: int = 520) -> str:
    # Short excerpts give the translator useful context without sending whole pages.
    sentences = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    content_tokens = query_tokens - {
        "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from",
        "how", "in", "is", "it", "of", "on", "or", "the", "to", "what", "with",
    }
    first_body_match = next(
        (
            index
            for index, sentence in enumerate(sentences[1:], start=1)
            if content_tokens & set(tokenize(sentence))
        ),
        None,
    )
    if first_body_match is not None:
        return " ".join(sentences[first_body_match : first_body_match + 3])[:width]
    candidates = [
        (len(query_tokens & set(tokenize(sentence))), -index, index)
        for index, sentence in enumerate(sentences)
        if index > 0 and query_tokens & set(tokenize(sentence))
    ]
    if candidates:
        # Prefer passages matching several query terms; this avoids returning
        # only a repeated page title when the useful definition follows it.
        start = max(candidates)[2]
        return " ".join(sentences[start : start + 3])[:width]
    return " ".join(text.split())[:width]
