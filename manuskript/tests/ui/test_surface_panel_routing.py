from manuskript.ui.surface_panel_routing import (
    SurfacePanelRoute,
    SurfacePanelRoutingController,
    SurfacePanelRoutingViews,
)


def a_controller(*, recorded=None):
    visible = {"core.project-tree": True, "plugin.notes": True}
    active = {"value": False}
    navigation_width = {"value": 200}
    events = []
    routes = [
        SurfacePanelRoute("core.project-tree", ("core.editor",), 187),
    ]

    def set_visible(panel_id, value):
        visible[panel_id] = value
        events.append((panel_id, value))

    controller = SurfacePanelRoutingController(SurfacePanelRoutingViews(
        project_active=lambda: active["value"],
        routes=lambda: tuple(routes),
        panel_visible=lambda panel_id: visible[panel_id],
        panel_extent=lambda _panel_id: 187,
        set_panel_visible=set_visible,
        remembered_visibility=lambda panel_id: (
            recorded if panel_id == "core.project-tree" else None
        ),
        navigation_extent=lambda: navigation_width["value"],
        restore_extents=lambda width, extents: events.append(
            ("layout", width, extents)
        ),
    ))
    return controller, active, visible, events, routes


def test_a_declared_companion_follows_surfaces_but_other_panels_do_not():
    controller, active, visible, events, _routes = a_controller()
    controller.surface_changed("core.general")
    assert events == []

    active["value"] = True
    controller.surface_changed("core.general")
    assert not visible["core.project-tree"]
    assert visible["plugin.notes"]
    assert events[-1] == ("layout", 200, {})

    controller.surface_changed("core.editor")
    assert visible["core.project-tree"]
    assert events[-1] == (
        "layout", 200, {"core.project-tree": 187},
    )


def test_a_reader_choice_is_remembered_separately_on_each_surface():
    controller, active, visible, _events, _routes = a_controller()
    active["value"] = True
    controller.surface_changed("core.general")
    visible["core.project-tree"] = True

    controller.surface_changed("core.editor")
    visible["core.project-tree"] = False

    controller.surface_changed("core.general")
    assert visible["core.project-tree"]

    controller.surface_changed("core.editor")
    assert not visible["core.project-tree"]


def test_the_saved_current_surface_choice_wins_over_the_new_default():
    controller, active, visible, _events, _routes = a_controller(recorded=True)
    active["value"] = True

    controller.surface_changed("core.general")

    assert visible["core.project-tree"]


def test_reactivating_the_same_surface_does_not_undo_a_reader_toggle():
    controller, active, visible, events, _routes = a_controller()
    active["value"] = True
    controller.surface_changed("core.editor")
    visible["core.project-tree"] = False
    events.clear()

    controller.surface_changed("core.editor")

    assert events == []
    assert not visible["core.project-tree"]


def test_a_routed_plugin_panel_mounted_late_joins_the_current_scene():
    controller, active, visible, events, routes = a_controller()
    active["value"] = True
    controller.surface_changed("core.editor")
    visible["plugin.companion"] = True
    routes.append(SurfacePanelRoute(
        "plugin.companion", ("core.general",), 260,
    ))
    events.clear()

    controller.panel_opened("plugin.companion")

    assert not visible["plugin.companion"]
    assert events == [
        ("plugin.companion", False),
        ("layout", 200, {"core.project-tree": 187}),
    ]
