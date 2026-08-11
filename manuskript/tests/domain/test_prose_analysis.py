import pytest

from manuskript.domain.assertion_dsl import encode_assertion_block
from manuskript.domain.prose_analysis import (
    ProseAnalysisOptions,
    ProseAnalyzer,
    ProseDocument,
)
from manuskript.domain.story_assertions import (
    Assertion,
    AssertionTerm,
    StoryReference,
)


def test_prose_analysis_reports_measurements_with_source_occurrences():
    documents = (
        ProseDocument(
            "one",
            "One",
            'She shook her head. “I know,” she said. She shook her head.\n\n'
            "The door was broken. It was very cold. color colour.",
        ),
        ProseDocument(
            "two", "Two", "She shook her head, then turned away."
        ),
    )
    report = ProseAnalyzer().analyze(
        documents,
        names=("Mara", "Maria", "Elias"),
        options=ProseAnalysisOptions(
            ngram_min=3,
            ngram_max=4,
            fillers=("very",),
        ),
    )

    assert report.documents[0].word_count > 10
    assert report.documents[0].sentence_lengths
    assert report.documents[0].paragraph_lengths
    assert report.documents[0].dialogue_word_ratio > 0
    repetition = next(
        item for item in report.repeated_phrases
        if item.pattern.casefold() == "she shook her"
    )
    assert repetition.count == 3
    assert {item.document_id for item in repetition.occurrences} == {
        "one", "two"
    }
    assert report.passive_candidates[0].pattern == "was broken"
    assert report.filler_phrases[0].pattern == "very"
    assert report.spelling_mixtures[0].pattern == "color / colour"
    assert report.similar_names[0].first == "Mara"
    assert report.similar_names[0].second == "Maria"


def test_analysis_masks_code_and_semantic_fences_from_prose_counts():
    assertion = Assertion(
        "secret", StoryReference("entity", "mara"), "knows",
        AssertionTerm.scalar("invisible semantic words"),
    )
    source = (
        "Visible prose.\n\n"
        "```example\nhidden code words\n```\n\n"
        + encode_assertion_block(assertion)
    )

    report = ProseAnalyzer().analyze((ProseDocument("one", "One", source),))

    assert report.documents[0].word_count == 2


def test_analysis_options_are_bounded_against_accidental_runaway_work():
    with pytest.raises(ValueError, match="N-gram"):
        ProseAnalysisOptions(ngram_max=100)
    with pytest.raises(ValueError, match="Maximum"):
        ProseAnalysisOptions(maximum_results=100000)


def test_analysis_is_deterministic_for_same_input():
    documents = (ProseDocument("one", "One", "Again and again and again."),)
    analyzer = ProseAnalyzer()

    assert analyzer.analyze(documents) == analyzer.analyze(documents)


def test_nearby_repetition_count_matches_unique_evidence_occurrences():
    report = ProseAnalyzer().analyze((
        ProseDocument("one", "One", "again again again"),
    ))

    pattern = next(
        item for item in report.nearby_repetitions
        if item.pattern == "again"
    )
    assert pattern.count == 3
    assert pattern.count == len(pattern.occurrences)
