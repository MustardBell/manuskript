import pytest

from manuskript.ui.workspace_lifetime import WorkspaceLifetime


class Component:
    def __init__(self, name, events):
        self.name = name
        self.events = events

    def dispose(self):
        self.events.append(self.name)


class BrokenComponent(Component):
    def dispose(self):
        self.events.append(self.name)
        raise RuntimeError("broken teardown")


def test_workspace_lifetime_releases_components_in_reverse_composition_order():
    events = []
    lifetime = WorkspaceLifetime()
    first = lifetime.own(Component("first", events))
    second = lifetime.own(Component("second", events))

    lifetime.dispose()

    assert events == ["second", "first"]
    assert len(lifetime) == 0
    assert first.name == "first"
    assert second.name == "second"


def test_workspace_lifetime_rejects_components_without_teardown():
    lifetime = WorkspaceLifetime()

    with pytest.raises(TypeError, match=r"must provide dispose\(\)"):
        lifetime.own(object())


def test_workspace_lifetime_can_be_disposed_again():
    events = []
    lifetime = WorkspaceLifetime()
    lifetime.own(Component("only", events))

    lifetime.dispose()
    lifetime.dispose()

    assert events == ["only"]


def test_one_broken_component_does_not_strand_the_rest(caplog):
    events = []
    lifetime = WorkspaceLifetime()
    lifetime.own(Component("first", events))
    lifetime.own(BrokenComponent("broken", events))
    lifetime.own(Component("last", events))

    lifetime.dispose()

    assert events == ["last", "broken", "first"]
    assert "BrokenComponent failed during disposal" in caplog.text
