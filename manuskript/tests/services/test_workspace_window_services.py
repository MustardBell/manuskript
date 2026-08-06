"""What the composition root hands a window, and nothing it can invent.

The point of the object is that absent is not a state it can be in. Every
field has to be said, including the ones that are legitimately nothing --
no plugin runtime means no plugin interface, which the application says out
loud rather than a window discovering it and building one.
"""

import dataclasses

import pytest

from manuskript.services.workspace_window_services import (
    WorkspaceWindowServices,
)


def a_service_set(**overrides):
    values = {
        name: object() for name in WorkspaceWindowServices.field_names()
    }
    values.update(overrides)
    return WorkspaceWindowServices(**values)


def test_every_service_has_to_be_said():
    """No defaults. A default is a fallback under another name: it lets a
    caller leave something out and get a working-looking window that is
    not part of the same application.
    """
    with pytest.raises(TypeError):
        WorkspaceWindowServices()

    for field in dataclasses.fields(WorkspaceWindowServices):
        assert field.default is dataclasses.MISSING, field.name
        assert field.default_factory is dataclasses.MISSING, field.name


def test_nothing_is_still_something_that_must_be_stated():
    services = a_service_set(plugin_runtime=None, plugin_contributions=None)

    assert services.plugin_runtime is None
    assert services.plugin_contributions is None


def test_the_services_cannot_be_swapped_after_composition():
    """Two windows hold the same object. One of them re-pointing a field
    would move the other's application out from under it.
    """
    services = a_service_set()

    with pytest.raises(dataclasses.FrozenInstanceError):
        services.panel_registry = object()


def test_the_field_names_are_the_fields():
    assert WorkspaceWindowServices.field_names() == tuple(
        field.name for field in dataclasses.fields(WorkspaceWindowServices)
    )
    # Named individually as well, so deleting one is a decision rather
    # than a test that quietly checks less than it did.
    assert set(WorkspaceWindowServices.field_names()) == {
        "application_preferences",
        "plugin_runtime",
        "plugin_option_store",
        "plugin_contributions",
        "media_types",
        "media_type_preferences",
        "panel_registry",
        "project_runtime",
        "window_registry",
    }
