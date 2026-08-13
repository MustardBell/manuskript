from dataclasses import replace

import pytest

from manuskript.plugins.api import EntitySnapshot, PluginFileSnapshot
from manuskript.plugins.capabilities import (
    CAPABILITY_ENTITIES_READ,
    CAPABILITY_ENTITIES_WRITE,
    CAPABILITY_PROJECT_DATA,
)
from manuskript.plugins.capability_rpc import (
    CapabilityRpcRouter,
    revision_token,
)
from manuskript.plugins.errors import (
    PluginConflictError,
    PluginProtocolError,
    PluginScopeError,
)
from manuskript.plugins.values import ContentEnvelope, api_value_codec


class EntityService:
    def __init__(self):
        self.entity = EntitySnapshot(
            "character:mara",
            "character",
            "Mara",
            "entities/character/mara.md",
        )

    def entities(self):
        return (self.entity,)

    def find(self, entity_id):
        return self.entity if entity_id == self.entity.id else None

    def update(self, entity_id, **changes):
        assert entity_id == self.entity.id
        self.entity = replace(self.entity, **changes)
        return self.entity

    def delete_everything(self):
        raise AssertionError("A non-contract method must never be called.")


def call(router, capability, operation, arguments=(), keyword_arguments=None,
         generation=4, revision=None):
    codec = api_value_codec()
    return router.handle("capability/call", {
        "capability": capability,
        "operation": operation,
        "arguments": codec.encode(tuple(arguments)),
        "keyword_arguments": codec.encode(dict(keyword_arguments or {})),
        "project_generation": generation,
        "expected_revision": revision,
    })


def router(service, declared=(CAPABILITY_ENTITIES_WRITE,), generation=None):
    current = generation if generation is not None else [4]
    return CapabilityRpcRouter(
        "example.remote",
        declared,
        lambda _name: service,
        lambda: current[0],
    )


def test_read_returns_a_portable_value_and_resource_revision():
    service = EntityService()
    response = call(
        router(service, (CAPABILITY_ENTITIES_READ,)),
        CAPABILITY_ENTITIES_READ,
        "find",
        (service.entity.id,),
    )

    value = api_value_codec().decode(response["value"])
    assert value == service.entity
    assert response["project_generation"] == 4
    assert response["revisions"] == {
        "EntitySnapshot:character:mara": revision_token(service.entity)
    }


def test_manifest_grant_and_method_table_are_both_enforced():
    service = EntityService()
    capability_router = router(
        service,
        (CAPABILITY_ENTITIES_READ,),
    )

    with pytest.raises(PluginScopeError, match="did not declare"):
        call(
            capability_router,
            CAPABILITY_ENTITIES_WRITE,
            "update",
            (service.entity.id,),
        )
    with pytest.raises(PluginScopeError, match="does not publish"):
        call(
            capability_router,
            CAPABILITY_ENTITIES_READ,
            "delete_everything",
        )


def test_stale_project_generation_is_rejected_before_service_resolution():
    resolved = []
    capability_router = CapabilityRpcRouter(
        "example.remote",
        (CAPABILITY_ENTITIES_READ,),
        lambda name: resolved.append(name),
        lambda: 8,
    )

    with pytest.raises(PluginConflictError) as caught:
        call(
            capability_router,
            CAPABILITY_ENTITIES_READ,
            "entities",
            generation=7,
        )

    assert caught.value.data == {
        "expected_generation": 8,
        "actual_generation": 7,
    }
    assert resolved == []


def test_revision_aware_write_rejects_stale_data_and_returns_new_revision():
    service = EntityService()
    capability_router = router(service)
    original_revision = revision_token(service.entity)

    with pytest.raises(PluginConflictError, match="resource revision"):
        call(
            capability_router,
            CAPABILITY_ENTITIES_WRITE,
            "update",
            (service.entity.id,),
            {"title": "Mara Vale"},
            revision="stale",
        )
    assert service.entity.title == "Mara"

    response = call(
        capability_router,
        CAPABILITY_ENTITIES_WRITE,
        "update",
        (service.entity.id,),
        {"title": "Mara Vale"},
        revision=original_revision,
    )
    changed = api_value_codec().decode(response["value"])
    assert changed.title == "Mara Vale"
    assert response["revisions"][
        "EntitySnapshot:character:mara"
    ] == revision_token(changed)


def test_revision_is_rejected_for_operations_that_do_not_use_one():
    with pytest.raises(PluginProtocolError, match="does not accept"):
        call(
            router(EntityService()),
            CAPABILITY_ENTITIES_WRITE,
            "entities",
            revision="invented",
        )


def test_method_schema_rejects_undeclared_arguments_before_python_dispatch():
    with pytest.raises(PluginProtocolError, match="does not accept keyword"):
        call(
            router(EntityService()),
            CAPABILITY_ENTITIES_WRITE,
            "entities",
            keyword_arguments={"reflect": True},
        )


def test_event_subscriptions_are_ordered_and_die_with_project_generation():
    generation = [3]
    capability_router = router(EntityService(), generation=generation)
    subscription = capability_router.handle("events/subscribe", {
        "topics": ["document.changed", "structure.changed"],
        "project_generation": 3,
    })

    first = capability_router.event_notifications(
        "document.changed", {"document_id": "scene:1"}
    )
    second = capability_router.event_notifications(
        "document.changed", {"document_id": "scene:1"}
    )
    assert first[0]["subscription_id"] == subscription["subscription_id"]
    assert first[0]["sequence"] == 1
    assert second[0]["sequence"] == 2

    generation[0] = 4
    capability_router.invalidate_subscriptions()
    assert capability_router.event_notifications(
        "document.changed", {"document_id": "scene:1"}
    ) == ()
    with pytest.raises(PluginConflictError):
        capability_router.handle("events/subscribe", {
            "topics": ["document.changed"],
            "project_generation": 3,
        })


def test_capability_call_shape_is_closed_not_extensible_by_accident():
    codec = api_value_codec()
    with pytest.raises(PluginProtocolError, match="exactly"):
        router(EntityService()).handle("capability/call", {
            "capability": CAPABILITY_ENTITIES_WRITE,
            "operation": "entities",
            "arguments": codec.encode(()),
            "keyword_arguments": codec.encode({}),
            "project_generation": 4,
            "expected_revision": None,
            "python_object": "please reflect over this",
        })


def test_new_plugin_file_accepts_null_revision_then_requires_current_token():
    class Files:
        value = None

        def read(self, path):
            return self.value if self.value and self.value.path == path else None

        def write(self, path, content):
            self.value = PluginFileSnapshot(path, content)
            return self.value

    files = Files()
    capability_router = router(files, (CAPABILITY_PROJECT_DATA,))
    content = ContentEnvelope("first", "text/plain")
    created = call(
        capability_router,
        CAPABILITY_PROJECT_DATA,
        "write",
        ("state.txt", content),
        revision=None,
    )
    snapshot = api_value_codec().decode(created["value"])
    current = revision_token(snapshot)

    with pytest.raises(PluginConflictError):
        call(
            capability_router,
            CAPABILITY_PROJECT_DATA,
            "write",
            ("state.txt", ContentEnvelope("stale", "text/plain")),
            revision=None,
        )
    changed = call(
        capability_router,
        CAPABILITY_PROJECT_DATA,
        "write",
        ("state.txt", ContentEnvelope("second", "text/plain")),
        revision=current,
    )
    assert api_value_codec().decode(changed["value"]).content.content == (
        "second"
    )
