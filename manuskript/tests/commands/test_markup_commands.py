from manuskript.commands import MarkupCommand, MarkupCommandRouter


class MarkupTarget:
    def __init__(self):
        self.calls = []

    def bold(self):
        self.calls.append(("bold", ()))

    def titleATX(self, level):
        self.calls.append(("titleATX", (level,)))


class ResolvingTarget:
    def __init__(self, target):
        self.target = target

    def markup_command_target(self, _command):
        return self.target


def test_router_dispatches_simple_and_parameterized_author_intent():
    target = MarkupTarget()
    router = MarkupCommandRouter(lambda: target)

    assert router.dispatch(MarkupCommand.BOLD)
    assert router.dispatch(MarkupCommand.HEADING_ATX_4)
    assert target.calls == [
        ("bold", ()),
        ("titleATX", (4,)),
    ]


def test_router_resolves_a_nested_markup_target():
    target = MarkupTarget()
    router = MarkupCommandRouter(
        lambda: ResolvingTarget(target)
    )

    assert router.can_dispatch(MarkupCommand.BOLD)
    assert router.dispatch(MarkupCommand.BOLD)
    assert target.calls == [("bold", ())]


def test_router_reports_missing_and_empty_targets_without_side_effects():
    target = MarkupTarget()
    router = MarkupCommandRouter(lambda: target)

    assert not router.can_dispatch(MarkupCommand.UNDERLINE)
    assert not router.dispatch(MarkupCommand.UNDERLINE)
    assert target.calls == []
    assert not MarkupCommandRouter(lambda: None).dispatch(
        MarkupCommand.BOLD
    )


def test_router_stops_resolver_cycles():
    first = ResolvingTarget(None)
    second = ResolvingTarget(first)
    first.target = second

    assert not MarkupCommandRouter(lambda: first).dispatch(
        MarkupCommand.CLEAR_FORMAT
    )
