from types import SimpleNamespace

import pytest

from manuskript.enums import Outline
from manuskript.domain.assertion_store import AssertionDocument
from manuskript.domain.canonical_project import CanonicalProject
from manuskript.domain.morphology import (
    GrammaticalForm,
    MorphologyComponent,
    MorphologyProfile,
)
from manuskript.domain.story_query import AssertionsWhere
from manuskript.plugins.api import (
    StoryReferenceValue,
    TemporalPointValue,
    WorkspaceDocument,
)
from manuskript.models import outlineItem, outlineModel
from manuskript.services.project_storage import ProjectStorage
from manuskript.ui.plugins.story_capabilities import (
    AssertionReadCapability,
    AssertionWriteCapability,
    EntityReadCapability,
    EntityWriteCapability,
    MorphologyRegistryCapability,
    QueryExecuteCapability,
    ReferenceReadCapability,
    ReferenceWriteCapability,
    TimelineReadCapability,
    ProjectSourceGateway,
)


class _ProjectManager:
    def __init__(self):
        self.storage = ProjectStorage()
        self.storage._canonical_project = CanonicalProject(format_version=2)
        self.storage.entity_catalog.replace((), writable=True)
        self.dirty = False
        self.flush_count = 0
        self.document_buffers = SimpleNamespace(flush=self._flush)

    def _flush(self):
        self.flush_count += 1

    def createEntity(self, entity_type, title, aliases=()):
        self.dirty = True
        return self.storage.create_entity(entity_type, title, aliases)

    def updateEntity(self, entity_id, **changes):
        self.dirty = True
        return self.storage.update_entity(entity_id, **changes)


class _Outline:
    def __init__(self, manager, document):
        self.manager = manager
        self._document = document

    def document(self, document_id):
        if str(document_id) == self._document.id:
            return self._document
        return None

    def set_text(self, document_id, text):
        if str(document_id) != self._document.id:
            raise KeyError(document_id)
        self._document = WorkspaceDocument(
            self._document.id,
            self._document.title,
            self._document.kind,
            str(text),
            self._document.compile,
            self._document.parent_id,
        )
        self.manager.storage.assertion_store.rebuild(
            (AssertionDocument(
                self._document.id,
                "Manuscript/Scene.md",
                self._document.text,
            ),),
            entity_ids=tuple(
                item.id for item in self.manager.storage.entity_catalog.entities
            ),
        )
        self.manager.storage.chronology.rebuild(
            self.manager.storage.assertion_store.assertions,
            narrative_ids=(self._document.id,),
        )
        return True


class _Provider:
    id = "example.story.simple-names"
    label = "Simple names"
    language = "en"
    component_roles = (("name", "Name"),)
    genders = ()

    @staticmethod
    def generate(component):
        return (GrammaticalForm("display", "Display", component.lemma.upper()),)

    @staticmethod
    def analyse(_surface, _component):
        return ()

    @staticmethod
    def validate(_component):
        return ()


@pytest.fixture
def story_services():
    manager = _ProjectManager()
    outline = _Outline(
        manager,
        WorkspaceDocument("scene", "Scene", "scene", "Mara waits."),
    )
    return manager, outline


def test_entity_capabilities_publish_snapshots_and_keep_mutation_commanded(
        story_services):
    manager, _outline = story_services
    reader = EntityReadCapability(manager)
    writer = EntityWriteCapability(manager)

    assert not hasattr(reader, "create")
    created = writer.create("character", "Mara Vale", ("Mara",))
    updated = writer.update(created.id, title="Mara Vane")

    assert manager.dirty
    assert reader.find(created.id).title == "Mara Vane"
    assert updated.id == created.id
    assert updated.path == created.path
    assert reader.exact_matches("Mara")[0].id == created.id
    with pytest.raises(TypeError, match="Unsupported"):
        writer.update(created.id, source_path="Elsewhere.md")


def test_reference_write_edits_authoritative_source_and_read_stays_read_only(
        story_services):
    manager, outline = story_services
    entity = EntityWriteCapability(manager).create("character", "Mara")
    reader = ReferenceReadCapability(manager)
    writer = ReferenceWriteCapability(manager, outline)

    changed = writer.insert("scene", 0, 4, entity.path[:-3], "Mara")

    assert changed == "[[Characters/Mara|Mara]] waits."
    assert outline.document("scene").text == changed
    assert manager.flush_count == 1
    assert not hasattr(reader, "insert")
    assert reader.complete("Mar")[0].document_id == entity.id
    with pytest.raises(ValueError, match="invalid"):
        writer.insert("scene", 0, 0, "bad]target")


def test_assertion_write_round_trips_source_provenance_and_canon_state(
        story_services):
    manager, outline = story_services
    entities = EntityWriteCapability(manager)
    mara = entities.create("character", "Mara")
    key = entities.create("object", "Brass Key")
    writer = AssertionWriteCapability(
        manager, outline, id_factory=lambda: "claim-1"
    )

    created = writer.append_relationship(
        "scene",
        StoryReferenceValue("entity", mara.id),
        "possesses",
        StoryReferenceValue("entity", key.id),
        qualifiers={"certainty": "explicit"},
        anchor="paragraph:key-transfer",
        note="Mara accepts the key.",
        valid_from=TemporalPointValue(
            "narrative", StoryReferenceValue("document", "scene")
        ),
    )

    assert created.document_id == "scene"
    assert created.source_start > 0
    assert created.source_end > created.source_start
    assert created.object.reference.id == key.id
    assert created.validity.valid_from.reference.id == "scene"
    assert "```manuskript-assertion" in outline.document("scene").text
    assert AssertionReadCapability(manager).find("claim-1").anchor == (
        "paragraph:key-transfer"
    )
    changed = writer.set_canon_state("claim-1", "tentative")
    assert changed.canon_state == "tentative"
    assert QueryExecuteCapability(manager).execute(
        AssertionsWhere(
            subject=StoryReferenceValue("entity", mara.id),
            predicate="possesses",
        )
    )[0].id == "claim-1"
    assert writer.remove("claim-1")
    assert "manuskript-assertion" not in outline.document("scene").text


def test_timeline_read_exposes_partial_order_and_temporal_fact_status(
        story_services):
    manager, outline = story_services
    writer = AssertionWriteCapability(
        manager, outline, id_factory=lambda: "location-1"
    )
    point = TemporalPointValue(
        "narrative", StoryReferenceValue("document", "scene")
    )
    writer.append_relationship(
        "scene",
        StoryReferenceValue("entity", "mara"),
        "located_at",
        StoryReferenceValue("entity", "vienna"),
        valid_from=point,
    )

    timeline = TimelineReadCapability(manager)
    facts = timeline.facts(
        point,
        subject=StoryReferenceValue("entity", "mara"),
        predicate="located_at",
    )

    assert facts[0].status == "active"
    assert facts[0].assertion.validity.valid_from == point
    assert timeline.compare(point, point) == "same"


def test_morphology_registration_is_namespaced_and_refreshes_surfaces(
        story_services):
    manager, _outline = story_services
    entity = EntityWriteCapability(manager).create("character", "Mara")
    profile = MorphologyProfile(
        _Provider.id,
        (MorphologyComponent("name", "Mara"),),
    )
    manager.storage.update_entity(
        entity.id, metadata=profile.apply_to(())
    )
    capability = MorphologyRegistryCapability(manager, "example.story")

    registered = capability.register(_Provider())

    assert registered.id == _Provider.id
    assert manager.storage.entity_catalog.exact_matches("MARA")[0].id == (
        entity.id
    )
    with pytest.raises(ValueError, match="must start"):
        capability.register(SimpleNamespace(
            id="someone.else.provider",
            label="Foreign",
            language="en",
        ))


def test_project_panel_source_gateway_uses_stable_document_commands(
        story_services):
    manager, _outline = story_services
    model = outlineModel()
    item = outlineItem(title="Scene", _type="md", parent=model.rootItem)
    item.setData(Outline.ID, "scene")
    item.setData(Outline.text, "Before.")
    manager.models = SimpleNamespace(outline=model)
    gateway = ProjectSourceGateway(manager)

    document = gateway.document("scene")
    changed = gateway.set_text("scene", "After.")

    assert document.text == "Before."
    assert changed
    assert item.text() == "After."
