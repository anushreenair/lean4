"""Complete word and general phrase coverage for a user query."""

from dataclasses import dataclass, replace
import re


# A simple regex keeps coverage predictable for ordinary English and Lean names.
WORD_RE = re.compile(r"[A-Za-z][A-Za-z0-9_'-]*")
STOPWORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "do", "for", "from",
    "how", "in", "is", "it", "of", "on", "or", "the", "to", "what", "with",
}


@dataclass(frozen=True)
class CoverageItem:
    # These fields show whether each word or phrase was actually checked and found.
    term: str
    type: str
    checked: bool = False
    result_found: bool = False
    source: str | None = None
    ambiguous: bool = False


@dataclass(frozen=True)
class QueryAnalysis:
    words: tuple[CoverageItem, ...]
    phrases: tuple[CoverageItem, ...]

    def update(self, term: str, found: bool, source: str | None, ambiguous: bool = False):
        # Frozen records are replaced rather than mutated, making the analysis easy to reason about.
        def update_items(items):
            return tuple(
                replace(item, checked=True, result_found=found, source=source, ambiguous=ambiguous)
                if item.term == term else item
                for item in items
            )

        return QueryAnalysis(update_items(self.words), update_items(self.phrases))


def normalize_words(query: str) -> list[str]:
    # Lowercase normalization makes searches case-insensitive while preserving the original query elsewhere.
    return [match.group(0).lower() for match in WORD_RE.finditer(query)]


def analyze_query(query: str) -> QueryAnalysis:
    # General n-grams find concepts such as "inductive type" without a hardcoded dictionary.
    words = normalize_words(query)
    phrases: list[str] = []
    for size in (3, 2):
        for start in range(len(words) - size + 1):
            window = words[start : start + size]
            if sum(word not in STOPWORDS for word in window) >= 2:
                phrase = " ".join(window)
                if phrase not in phrases:
                    phrases.append(phrase)
    return QueryAnalysis(
        words=tuple(CoverageItem(word, "word") for word in words),
        phrases=tuple(CoverageItem(phrase, "phrase") for phrase in phrases),
    )
