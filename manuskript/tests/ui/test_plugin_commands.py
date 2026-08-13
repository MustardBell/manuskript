import threading
import time

from PyQt5.QtWidgets import QAction, qApp

from manuskript.plugins.api import CommandContribution, ExtensionDescriptor
from manuskript.tests import prepare_test_application


def test_host_owned_plugin_commands_are_keyboard_actions_and_project_scoped():
    _app, window = prepare_test_application()
    invoked = threading.Event()
    registrar = window.pluginRuntime.registry.registrar("example.commands")
    registrar.register_command(CommandContribution(
        ExtensionDescriptor(
            "example.commands.global",
            "Run global check",
            "Run without an open project.",
        ),
        invoke=lambda: invoked.set() or "Check complete",
        shortcut="Ctrl+Alt+G",
        project_required=False,
    ))
    registrar.register_command(CommandContribution(
        ExtensionDescriptor(
            "example.commands.project",
            "Run project check",
        ),
        invoke=lambda: None,
        project_required=True,
    ))
    window.pluginRuntime.registry.install(
        "example.commands", registrar.contributions
    )
    window.pluginContributions.announce()
    qApp.processEvents()

    global_action = window.findChild(
        QAction, "pluginCommand.example.commands.global"
    )
    project_action = window.findChild(
        QAction, "pluginCommand.example.commands.project"
    )
    assert global_action.isEnabled()
    assert global_action.shortcut().toString() == "Ctrl+Alt+G"
    assert global_action.statusTip() == "Run without an open project."
    assert not project_action.isEnabled()

    global_action.trigger()
    deadline = time.monotonic() + 2
    while not invoked.is_set():
        assert time.monotonic() < deadline
        qApp.processEvents()
        time.sleep(0.005)

    window.pluginRuntime.registry.remove_plugin("example.commands")
    window.pluginContributions.announce()
    window.close()
