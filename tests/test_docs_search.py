from docs_index import Document, DocumentIndex


def fixture_index():
    return DocumentIndex(
        [
            Document(
                title="Inductive Types",
                url="https://lean-lang.org/doc/inductive.html",
                headings=("Inductive Types",),
                text="An inductive type is defined by constructors. Inductive declarations.",
            ),
            Document(
                title="Theorem Proving",
                url="https://lean-lang.org/doc/theorems.html",
                headings=("Theorem",),
                text="A theorem is a named proposition with a proof.",
            ),
        ]
    )


def test_search_returns_relevant_document_with_source_fields():
    result = fixture_index().search("inductive type", top_k=1)[0]

    assert result.title == "Inductive Types"
    assert result.url.endswith("inductive.html")
    assert result.score > 0
    assert result.text


def test_search_empty_index_returns_no_results():
    assert DocumentIndex([]).search("inductive") == []
