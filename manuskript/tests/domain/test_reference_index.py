from manuskript.domain.reference_index import (
    ReferenceDocument,
    ReferenceIndex,
    ReferenceResolution,
)


def _documents():
    return (
        ReferenceDocument(
            "scene", "Manuscript/Scene.md", "Scene",
            "[[Characters/Mara|Mara]] meets [[Vienna]]. "
            "[[missing]] [[https://example.com|source]]",
        ),
        ReferenceDocument(
            "mara", "Characters/Mara.md", "Mara", "Character notes.",
        ),
        ReferenceDocument(
            "vienna", "Places/Vienna.md", "Vienna", "Place notes.",
        ),
    )


def test_reference_index_resolves_paths_titles_missing_and_external_targets():
    index = ReferenceIndex()

    references = index.rebuild(_documents())

    assert [item.resolution for item in references] == [
        ReferenceResolution.RESOLVED,
        ReferenceResolution.RESOLVED,
        ReferenceResolution.MISSING,
        ReferenceResolution.EXTERNAL,
    ]
    assert tuple(item.source_document_id for item in index.backlinks("mara")) == (
        "scene",
    )
    assert tuple(item.raw_target for item in index.broken()) == ("missing",)


def test_duplicate_short_titles_are_ambiguous_but_full_paths_resolve():
    documents = (
        ReferenceDocument("a", "Places/A/Station.md", "Station", ""),
        ReferenceDocument("b", "Places/B/Station.md", "Station", ""),
        ReferenceDocument(
            "scene", "Manuscript/Scene.md", "Scene",
            "[[Station]] [[Places/A/Station]]",
        ),
    )

    references = ReferenceIndex().rebuild(documents)

    assert references[0].resolution is ReferenceResolution.AMBIGUOUS
    assert references[1].resolved_target_id == "a"


def test_cooccurrence_is_derived_only_from_explicit_references():
    index = ReferenceIndex()
    index.rebuild(_documents() + (
        ReferenceDocument(
            "other", "Manuscript/Other.md", "Other",
            "Mara is prose, not a reference. [[Places/Vienna]].",
        ),
    ))

    assert tuple(
        document.id for document in index.cooccurring("mara", "vienna")
    ) == ("scene",)


def test_path_refactor_changes_only_resolved_target_spans():
    index = ReferenceIndex()
    index.rebuild(_documents())

    refactor = index.plan_path_refactor("mara", "People/Mara Vale.md")

    assert refactor.updated_sources["scene"].startswith(
        "[[People/Mara Vale|Mara]] meets"
    )
    assert "[[Vienna]]" in refactor.updated_sources["scene"]
    assert "[[missing]]" in refactor.updated_sources["scene"]


def test_incremental_update_rebuilds_resolution_against_current_sources():
    index = ReferenceIndex()
    index.rebuild(_documents())

    index.update(ReferenceDocument(
        "scene", "Manuscript/Scene.md", "Scene", "[[Places/Vienna]]"
    ))

    assert not index.backlinks("mara")
    assert len(index.backlinks("vienna")) == 1


def test_reference_completion_is_deterministic_and_inserts_stable_paths():
    index = ReferenceIndex()
    index.rebuild(_documents())

    by_title = index.complete("mar")
    by_path = index.complete("places/v")

    assert tuple(item.target for item in by_title) == ("Characters/Mara",)
    assert tuple(item.document_id for item in by_path) == ("vienna",)
    assert index.resolve(by_path[0].target)[1].id == "vienna"
