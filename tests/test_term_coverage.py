from term_analyzer import analyze_query


def test_every_word_is_recorded_and_checked():
    analysis = analyze_query("What is an inductive type in Lean?")

    assert [item.term for item in analysis.words] == [
        "what",
        "is",
        "an",
        "inductive",
        "type",
        "in",
        "lean",
    ]
    assert all(item.type == "word" for item in analysis.words)


def test_general_phrase_extraction_finds_meaningful_concept():
    analysis = analyze_query("What is an inductive type in Lean?")

    assert any(item.term == "inductive type" for item in analysis.phrases)
    assert not any(item.term == "what is" for item in analysis.phrases)
