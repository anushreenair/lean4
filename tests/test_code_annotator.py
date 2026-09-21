from pathlib import Path

from code_annotator import LeanCodeAnnotator
from docs_index import Document, DocumentIndex


SNIPPET = "theorem foo (n : Nat) : n + 0 = n := by\n  simp"


def test_theorem_snippet_is_tokenized_and_classified():
    annotator = LeanCodeAnnotator(
        DocumentIndex(
            [
                Document(
                    "Theorems",
                    "https://lean-lang.org/doc/reference/latest/Definitions/Theorems/",
                    ("Theorems",),
                    "Theorem declarations use the theorem keyword. simp is a tactic.",
                )
            ]
        ),
        skill_path=Path("SKILL.md"),
    )

    result = annotator.annotate(SNIPPET)
    labels = [(item.text, item.category) for item in result.tokens]

    assert ("theorem", "keyword") in labels
    assert ("foo", "identifier") in labels
    assert ("(", "syntax") in labels
    assert ("+", "notation") in labels
    assert ("0", "numeral") in labels
    assert ("simp", "tactic identifier") in labels
    assert result.documentation_checked


def test_annotation_preserves_token_order_and_line_numbers():
    annotator = LeanCodeAnnotator(DocumentIndex([]), skill_path=Path("SKILL.md"))

    result = annotator.annotate("def foo : Nat := 0\n#check foo")

    assert [item.text for item in result.tokens[:4]] == ["def", "foo", ":", "Nat"]
    assert result.tokens[0].line == 1
    assert any(item.text == "#check" and item.line == 2 for item in result.tokens)


def test_annotation_records_searches_before_returning_labels():
    class RecordingIndex:
        def __init__(self):
            self.queries = []

        def search(self, query, top_k=5):
            self.queries.append(query)
            return []

    index = RecordingIndex()
    annotator = LeanCodeAnnotator(index, skill_path=Path("SKILL.md"))

    result = annotator.annotate("theorem foo : True := by trivial")

    assert result.documentation_checked
    assert index.queries[:2] == ["theorem", "foo"]
