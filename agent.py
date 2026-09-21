"""Documentation-first orchestration for every user request."""

from dataclasses import asdict, dataclass
from pathlib import Path
import re

from docs_index import DocumentIndex, SearchResult
from llm import ExplanationProvider, ExtractiveExplanationProvider
from term_analyzer import QueryAnalysis, analyze_query


@dataclass(frozen=True)
class LoadedSkill:
    path: str
    instructions: str
    loaded: bool


@dataclass(frozen=True)
class AgentAnswer:
    # Immutable results make it safe to preserve and serialize the complete answer record.
    query: str
    answer: str
    sources: tuple[SearchResult, ...]
    coverage: QueryAnalysis
    searches: tuple[str, ...]
    skill_loaded: bool
    source_type: str
    fallback_reason: str | None = None

    def to_json(self) -> dict:
        value = asdict(self)
        value["sources"] = [source.to_json() for source in self.sources]
        value["coverage"] = {
            "words": [asdict(item) for item in self.coverage.words],
            "phrases": [asdict(item) for item in self.coverage.phrases],
        }
        return value


def load_skill(path: Path) -> LoadedSkill:
    # Loading the instructions at runtime ensures the documentation-first rule is present.
    try:
        instructions = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Required agent skill could not be loaded: {path}") from exc
    if "official Lean documentation" not in instructions:
        raise RuntimeError(f"Skill does not contain documentation-first instructions: {path}")
    return LoadedSkill(str(path), instructions, True)


class DocumentationFirstAgent:
    def __init__(self, index, provider: ExplanationProvider | None, skill_path: Path):
        self.index = index
        # The extractive provider keeps the tool useful when no API key is configured.
        self.provider = provider or ExtractiveExplanationProvider()
        self.skill = load_skill(skill_path)

    def answer(self, query: str) -> AgentAnswer:
        analysis = analyze_query(query)
        searches: list[str] = []
        all_results: list[SearchResult] = []
        word_results: list[SearchResult] = []
        phrase_results: list[SearchResult] = []

        # Every word and phrase enters the same documentation search interface so nothing is silently missed.
        for item in analysis.words:
            results = self._search(item.term, searches)
            analysis = analysis.update(item.term, bool(results), results[0].url if results else None)
            all_results.extend(results)
            word_results.extend(results)
        for item in analysis.phrases:
            results = self._search(item.term, searches)
            analysis = analysis.update(item.term, bool(results), results[0].url if results else None)
            all_results.extend(results)
            phrase_results.extend(results)

        primary = self._search(query, searches)
        all_results.extend(primary)
        preferred_results = list(primary)
        if _needs_clarification(primary):
            # A focused retry helps when a full natural-language question scores poorly.
            focused = " ".join(item.term for item in analysis.words if item.term not in {"what", "is", "a", "an", "the", "in", "of", "to", "how", "explain"})
            second = self._search(focused or query, searches)
            all_results.extend(second)
            preferred_results.extend(second)

        # Keep a short, unique source list so the answer stays readable and traceable.
        sources = _unique_results(preferred_results + phrase_results + word_results + all_results)
        try:
            generated = self.provider.explain(query, sources, analysis)
            source_type = "llm_documentation_context" if not isinstance(self.provider, ExtractiveExplanationProvider) else "documentation_extract"
            fallback_reason = None
        except Exception as exc:
            # Provider failures should not erase the documentation-backed result.
            generated = ExtractiveExplanationProvider().explain(query, sources, analysis)
            source_type = "documentation_extract"
            fallback_reason = f"Explanation provider unavailable: {exc}"
        return AgentAnswer(query, generated, tuple(sources), analysis, tuple(searches), self.skill.loaded, source_type, fallback_reason)

    def _search(self, query: str, searches: list[str]) -> list[SearchResult]:
        searches.append(query)
        return self.index.search(query, top_k=5)


def _needs_clarification(results: list[SearchResult]) -> bool:
    return not results or results[0].score < 0.75


def _unique_results(results: list[SearchResult]) -> list[SearchResult]:
    unique: dict[str, SearchResult] = {}
    for result in results:
        unique.setdefault(result.url, result)
    return list(unique.values())[:5]
