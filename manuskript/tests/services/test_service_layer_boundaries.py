"""Services sit under the windows, and must not reach back up into them.

A project service that imports a widget module inverts the layering: the
thing that owns the text asks the thing that displays it what the text
says. It happened exactly once, and quietly -- a lazy import inside a
method, invisible to any import-order check, added while fixing something
else.

So the rule is checked over the whole package rather than the one module
that broke it. Adding a service that needs something from the interface
means either the something belongs lower down, or the service belongs
higher up.
"""

from pathlib import Path

from manuskript import services


#: Read from the source rather than the import graph on purpose. A lazy
#: import inside a function never shows up in sys.modules until it runs,
#: which is precisely how this got in.
FORBIDDEN = "manuskript.ui"


def service_modules():
    return sorted(Path(services.__file__).parent.glob("*.py"))


def test_no_service_reaches_up_into_the_interface():
    offenders = [
        path.name
        for path in service_modules()
        if FORBIDDEN in path.read_text(encoding="utf-8")
    ]

    assert offenders == [], (
        "these services name {}: {}".format(FORBIDDEN, ", ".join(offenders))
    )


def test_there_are_services_to_check():
    """A glob that matches nothing would pass the test above silently."""
    assert len(service_modules()) > 10
