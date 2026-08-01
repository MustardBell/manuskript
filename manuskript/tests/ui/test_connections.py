from PyQt5.QtCore import QObject, pyqtSignal

from manuskript.ui.connections import SignalConnectionRegistry


class Emitter(QObject):
    changed = pyqtSignal(int)


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
