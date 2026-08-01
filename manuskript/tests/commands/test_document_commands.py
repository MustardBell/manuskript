from manuskript.commands import DocumentCommand, DocumentCommandRouter


class CommandTarget:
    def __init__(self):
        self.calls = []

    def copy(self):
        self.calls.append(DocumentCommand.COPY)

    def splitCursor(self):
        self.calls.append(DocumentCommand.SPLIT_CURSOR)


class ResolvingTarget:
    def __init__(self, target):
        self.target = target
        self.resolved_commands = []

    def document_command_target(self, command):
        self.resolved_commands.append(command)
        return self.target


def test_router_dispatches_to_a_direct_capable_target():
    target = CommandTarget()
    router = DocumentCommandRouter(lambda: target)

    assert router.can_dispatch(DocumentCommand.COPY)
    assert router.dispatch(DocumentCommand.COPY, False)
    assert target.calls == [DocumentCommand.COPY]


def test_router_resolves_nested_editor_targets():
    endpoint = CommandTarget()
    editor = ResolvingTarget(endpoint)
    main_editor = ResolvingTarget(editor)
    router = DocumentCommandRouter(lambda: main_editor)

    assert router.dispatch(DocumentCommand.SPLIT_CURSOR)
    assert endpoint.calls == [DocumentCommand.SPLIT_CURSOR]
    assert main_editor.resolved_commands == [DocumentCommand.SPLIT_CURSOR]
    assert editor.resolved_commands == [DocumentCommand.SPLIT_CURSOR]


def test_router_reports_unsupported_commands_without_side_effects():
    target = CommandTarget()
    router = DocumentCommandRouter(lambda: target)

    assert not router.can_dispatch(DocumentCommand.MERGE)
    assert not router.dispatch(DocumentCommand.MERGE)
    assert target.calls == []


def test_router_handles_an_empty_target():
    router = DocumentCommandRouter(lambda: None)

    assert not router.can_dispatch(DocumentCommand.CUT)
    assert not router.dispatch(DocumentCommand.CUT)


def test_router_stops_resolver_cycles():
    first = ResolvingTarget(None)
    second = ResolvingTarget(first)
    first.target = second
    router = DocumentCommandRouter(lambda: first)

    assert not router.dispatch(DocumentCommand.DELETE)
