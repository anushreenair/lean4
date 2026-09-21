from pathlib import Path

from code_understanding import DocumentationFirstCodeAgent
from docs_index import Document, SearchResult


CODE = "theorem foo (n : Nat) : n + 0 = n := by\n  simp"


class RecordingIndex:
    def __init__(self, events):
        self.events = events
        self.queries = []

    def search(self, query, top_k=5):
        self.events.append("search")
        self.queries.append(query)
        return [
            SearchResult(
                query, "Theorems", "https://lean-lang.org/doc/theorems", "Theorems",
                f"Official Lean documentation about {query}.", 1.0,
            )
        ]


class RecordingTranslator:
    def __init__(self, events):
        self.events = events

    def translate(self, code, context):
        self.events.append("translate")
        return "This proves that adding zero to a natural number leaves it unchanged."


def test_code_is_broken_into_requested_documented_categories():
    events = []
    agent = DocumentationFirstCodeAgent(
        RecordingIndex(events), RecordingTranslator(events), skill_path=Path("SKILL.md")
    )

    result = agent.explain(CODE)
    categories = {thing.category for thing in result.things}
    texts = {thing.text for thing in result.things}

    assert "Commands/declarations" in categories
    assert "Keywords" in categories
    assert "Identifiers / names" in categories
    assert "Types" in categories
    assert "Binders" in categories
    assert "Terms / expressions" in categories
    assert "Tactics" in categories
    assert "theorem" in texts
    assert "(n : Nat)" in texts
    assert "Nat" in texts
    assert result.documentation_checked


def test_all_documented_context_is_retrieved_before_translation():
    events = []
    agent = DocumentationFirstCodeAgent(
        RecordingIndex(events), RecordingTranslator(events), skill_path=Path("SKILL.md")
    )

    result = agent.explain(CODE)

    assert events.index("search") < events.index("translate")
    assert result.english == "This proves that adding zero to a natural number leaves it unchanged."
    assert result.sources == ("https://lean-lang.org/doc/theorems",)


def test_no_llm_translator_still_returns_contextual_english():
    index = RecordingIndex([])
    agent = DocumentationFirstCodeAgent(index, translator=None, skill_path=Path("SKILL.md"))

    result = agent.explain(CODE)

    assert "theorem" in result.english.lower()
    assert result.sources


def test_fallback_translation_uses_definition_body_and_declaration_name():
    agent = DocumentationFirstCodeAgent(RecordingIndex([]), translator=None, skill_path=Path("SKILL.md"))

    definition = agent.explain("def double (n : Nat) : Nat := n + n")
    inductive = agent.explain("inductive Color where\n  | red\n  | blue")

    assert "double" in definition.english
    assert "n + n" in definition.english
    assert "Color" in inductive.english
