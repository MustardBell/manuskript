from functools import partial
import gc
import weakref

from PyQt5.QtCore import QObject, pyqtSignal

from manuskript.ui.connections import SignalConnectionRegistry


class Emitter(QObject):
    changed = pyqtSignal(int)


class Receiver:
    def __init__(self, received):
        self.received = received

    def receive(self, prefix, value):
        self.received.append((prefix, value))


def test_registry_disconnects_owned_signal_connections():
    emitter = Emitter()
    received = []
    connections = SignalConnectionRegistry()
    connections.connect(emitter.changed, received.append)

    emitter.changed.emit(1)
    connections.disconnect_all()
    emitter.changed.emit(2)

    assert received == [1]
    assert len(connections) == 0


def test_registry_disconnects_exact_lambda_instance():
    emitter = Emitter()
    received = []
    connections = SignalConnectionRegistry()
    connections.connect(emitter.changed, lambda value: received.append(value))

    connections.disconnect_all()
    emitter.changed.emit(1)

    assert received == []


def test_registry_can_be_reused_after_disconnect():
    emitter = Emitter()
    received = []
    connections = SignalConnectionRegistry()

    connections.connect(emitter.changed, received.append)
    connections.disconnect_all()
    connections.connect(emitter.changed, received.append)
    emitter.changed.emit(1)

    assert received == [1]
    assert len(connections) == 1


def test_weak_connection_does_not_own_a_partial_bound_receiver():
    emitter = Emitter()
    received = []
    receiver = Receiver(received)
    receiver_ref = weakref.ref(receiver)
    connections = SignalConnectionRegistry()
    connections.connect_weak(
        emitter.changed,
        partial(receiver.receive, "changed"),
    )

    emitter.changed.emit(1)
    del receiver
    gc.collect()
    emitter.changed.emit(2)

    assert received == [("changed", 1)]
    assert receiver_ref() is None


def test_weak_connection_preserves_signal_argument_adaptation():
    emitter = Emitter()
    calls = []
    connections = SignalConnectionRegistry()
    connections.connect_weak(emitter.changed, lambda: calls.append("called"))

    emitter.changed.emit(1)

    assert calls == ["called"]
