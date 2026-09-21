from pathlib import Path

from agent import DocumentationFirstAgent
from docs_index import Document, DocumentIndex, SearchResult
from llm import ExplanationProvider


class RecordingProvider(ExplanationProvider):
    def __init__(self, events):
        self.events = events

    def explain(self, query, documents, coverage):
        self.events.append("generate")
        return "A documented explanation."


class RecordingIndex:
    def __init__(self, events, results):
        self.events = events
        self.results = results
        self.queries = []

    def search(self, query, top_k=5):
        self.events.append("search")
        self.queries.append(query)
        return self.results


def docs():
    return [
        Document(
            "Inductive Types",
            "https://lean-lang.org/doc/inductive.html",
            ("Inductive Types",),
            "An inductive type is defined by constructors.",
        )
    ]


def result_for(document, score=1.0):
    return SearchResult("query", document.title, document.url, document.headings[0], document.text, score)


def test_documentation_search_happens_before_answer_generation_and_sources_survive():
    events = []
    result = docs()[0]
    agent = DocumentationFirstAgent(
        RecordingIndex(events, [result_for(result)]), RecordingProvider(events), skill_path=Path("SKILL.md")
    )

    answer = agent.answer("What is an inductive type in Lean?")

    assert events.index("search") < events.index("generate")
    assert answer.answer == "A documented explanation."
    assert answer.sources[0].url == result.url
    assert answer.skill_loaded
    assert all(item.checked for item in answer.coverage.words)


def test_weak_initial_result_causes_contextual_second_search():
    events = []
    weak = Document("General", "https://lean-lang.org/doc/general.html", ("General",), "general")
    strong = docs()[0]
    index = RecordingIndex(events, [result_for(weak, score=0.1)])
    agent = DocumentationFirstAgent(index, RecordingProvider(events), skill_path=Path("SKILL.md"))

    agent.answer("What is a constructor in an inductive type?")

    assert len(index.queries) >= 2
    assert "constructor" in index.queries[-1]


def test_no_llm_key_still_produces_extractive_answer(tmp_path: Path):
    result = docs()[0]
    agent = DocumentationFirstAgent(
        DocumentIndex([result]), provider=None, skill_path=Path("SKILL.md")
    )

    answer = agent.answer("What is an inductive type?")

    assert answer.answer
    assert answer.source_type == "documentation_extract"
    assert answer.sources
