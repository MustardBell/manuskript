"""Where every open panel is, across the whole application.

A panel declared to exist once in the application has to be findable
wherever it currently is: a second window asking for it must be told to
move the one that exists rather than build a second answering to the same
name. So somebody has to know all the hosts, and that somebody cannot be
one of them.

It used to be a class attribute on PanelHost -- a WeakSet every host added
itself to on construction. That works, and hid two things. It was global
state, so two hosts in a test could see each other however carefully the
test had built them separately; and it was reachable from anywhere that
could import the class, which is the shape a Service Locator grows from.

One directory per application now, composed with everything else and
handed to the hosts. Hosts are still held weakly: a closed window must not
be kept alive by being findable.
"""

import weakref


class PanelInstanceDirectory:
    """The panel hosts of one application, and what each of them holds."""

    def __init__(self):
        self._hosts = weakref.WeakSet()

    def add(self, host):
        self._hosts.add(host)
        return host

    def remove(self, host):
        self._hosts.discard(host)

    @property
    def hosts(self):
        return tuple(self._hosts)

    def holder(self, panel_id, besides=None):
        """The host that has this panel, if any other window does.

        ``besides`` is the host asking, which is never the answer: it has
        already looked at what it holds itself.
        """
        for host in tuple(self._hosts):
            if host is besides:
                continue
            if host.instance(panel_id) is not None:
                return host
        return None

    def locate(self, panel_id):
        """Every host showing this panel, in no particular order.

        More than one is possible for a per-window panel, and is the
        ordinary case: each window has its own.
        """
        return tuple(
            host
            for host in tuple(self._hosts)
            if host.instance(panel_id) is not None
        )
