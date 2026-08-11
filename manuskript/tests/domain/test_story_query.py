from manuskript.domain.assertion_dsl import encode_assertion_block
from manuskript.domain.assertion_store import AssertionDocument, AssertionStore
from manuskript.domain.canonical_project import EntityRecord, OutlineDocument
from manuskript.domain.entity_catalog import EntityCatalog
from manuskript.domain.reference_index import ReferenceDocument, ReferenceIndex
from manuskript.domain.story_assertions import (
    Assertion,
    AssertionQualifier,
    AssertionTerm,
    CanonState,
    StoryReference,
)
import pytest

from manuskript.domain.story_query import (
    All,
    And,
    AssertionsWhere,
    DocumentsReferencing,
    EntitiesRelatedTo,
    EntitiesWhere,
    Not,
    Or,
    QueryResult,
    QueryScope,
    StoryQueryEngine,
)


def _entity(identifier, title, entity_type="character"):
    return EntityRecord(
        OutlineDocument(
            identifier, title, "entity", "",
            source_path="Entities/{}.md".format(title),
        ),
        entity_type,
    )


def _engine():
    entities = EntityCatalog()
    entities.replace((
        _entity("mara", "Mara"),
        _entity("elias", "Elias"),
        _entity("key", "Brass Key", "object"),
    ))
    references = ReferenceIndex()
    references.rebuild((
        ReferenceDocument(
            "scene-1", "Scene 1.md", "Scene 1",
            "[[Entities/Mara|Mara]] meets [[Entities/Elias|Elias]].",
        ),
        ReferenceDocument(
            "scene-2", "Scene 2.md", "Scene 2",
            "[[Entities/Mara|Mara]] takes [[Entities/Brass Key|the key]].",
        ),
        *(ReferenceDocument(
            entity.id,
            entity.document.source_path,
            entity.title,
            "",
        ) for entity in entities.entities),
    ))
    claims = (
        Assertion(
            "owns-key",
            StoryReference("entity", "mara"),
            "possesses",
            AssertionTerm.referencing("entity", "key"),
            (AssertionQualifier("certainty", "explicit"),),
            canon_state=CanonState.CANON,
        ),
        Assertion(
            "trusts-elias",
            StoryReference("entity", "mara"),
            "trusts",
            AssertionTerm.referencing("entity", "elias"),
            canon_state=CanonState.TENTATIVE,
        ),
    )
    assertions = AssertionStore()
    assertions.rebuild((AssertionDocument(
        "scene-2",
        "Scene 2.md",
        "\n".join(encode_assertion_block(item) for item in claims),
    ),), entity_ids=("mara", "elias", "key"))
    return StoryQueryEngine(entities, references, assertions)


def test_assertion_query_filters_explicit_state_and_provenance():
    engine = _engine()
    query = AssertionsWhere(
        subject=StoryReference("entity", "mara"),
        predicate="possesses",
        canon_states=(CanonState.CANON,),
        source_document_ids=("scene-2",),
        qualifiers=(("certainty", "explicit"),),
    )

    assert engine.execute(query) == (
        QueryResult(QueryScope.ASSERTION, "owns-key"),
    )


def test_reference_query_requires_all_entities_without_inferring_presence():
    engine = _engine()

    both = engine.execute(DocumentsReferencing(("mara", "elias")))
    mara_or_key = engine.execute(DocumentsReferencing(
        ("mara", "key"), require_all=False
    ))

    assert both == (QueryResult(QueryScope.DOCUMENT, "scene-1"),)
    assert mara_or_key == (
        QueryResult(QueryScope.DOCUMENT, "scene-1"),
        QueryResult(QueryScope.DOCUMENT, "scene-2"),
    )


def test_relationship_and_entity_queries_return_stable_identities():
    engine = _engine()

    related = engine.execute(EntitiesRelatedTo(
        StoryReference("entity", "mara"), direction="outgoing"
    ))
    objects = engine.execute(EntitiesWhere(entity_type="object"))

    assert related == (
        QueryResult(QueryScope.ENTITY, "elias"),
        QueryResult(QueryScope.ENTITY, "key"),
    )
    assert objects == (QueryResult(QueryScope.ENTITY, "key"),)


def test_boolean_query_ast_uses_typed_set_operations():
    engine = _engine()
    all_entities = All(QueryScope.ENTITY)
    characters = EntitiesWhere(entity_type="character")
    mara = EntitiesWhere(surface="Mara")

    assert engine.execute(And((characters, mara))) == (
        QueryResult(QueryScope.ENTITY, "mara"),
    )
    assert engine.execute(Not(QueryScope.ENTITY, characters)) == (
        QueryResult(QueryScope.ENTITY, "key"),
    )
    assert engine.execute(Or((mara, Not(QueryScope.ENTITY, characters)))) == (
        QueryResult(QueryScope.ENTITY, "key"),
        QueryResult(QueryScope.ENTITY, "mara"),
    )
    assert engine.execute(all_entities) == (
        QueryResult(QueryScope.ENTITY, "elias"),
        QueryResult(QueryScope.ENTITY, "key"),
        QueryResult(QueryScope.ENTITY, "mara"),
    )


def test_boolean_query_ast_refuses_mixed_or_empty_scopes():
    with pytest.raises(ValueError, match="share one scope"):
        Or((EntitiesWhere(), AssertionsWhere()))
    with pytest.raises(ValueError, match="at least one"):
        And(())
    with pytest.raises(ValueError, match="scope must match"):
        Not(QueryScope.DOCUMENT, EntitiesWhere())
