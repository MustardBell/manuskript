class SignalConnectionRegistry:
    """Own a group of Qt signal connections and tear them down together."""

    def __init__(self):
        self._connections = []

    def __len__(self):
        return len(self._connections)

    def connect(self, signal, slot, connection_type=None):
        if connection_type is None:
            signal.connect(slot)
        else:
            signal.connect(slot, connection_type)
        self._connections.append((signal, slot))

    def disconnect_all(self):
        for signal, slot in reversed(self._connections):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                # A Qt owner may already have destroyed the underlying object.
                pass
        self._connections.clear()
