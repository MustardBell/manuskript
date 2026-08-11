from functools import partial
from inspect import signature
from weakref import ref


class _WeakCallable:
    """Invoke a callable without making its bound owner a signal owner.

    PyQt keeps Python callables on the C++ signal connection.  A child
    action connected to a bound window method can consequently keep the
    whole deleted window wrapper alive.  This adapter retains ordinary
    functions and immutable arguments, but resolves bound methods and
    bound callables through weak references at invocation time.
    """

    def __init__(self, callback):
        self._partial = isinstance(callback, partial)
        self._callable = self._store(callback.func if self._partial else callback)
        self._args = (
            tuple(self._store(value) for value in callback.args)
            if self._partial
            else ()
        )
        self._keywords = (
            {
                key: self._store(value)
                for key, value in (callback.keywords or {}).items()
            }
            if self._partial
            else {}
        )
        try:
            parameters = signature(callback).parameters.values()
        except (TypeError, ValueError):
            self._positional_limit = None
        else:
            if any(parameter.kind == parameter.VAR_POSITIONAL
                   for parameter in parameters):
                self._positional_limit = None
            else:
                self._positional_limit = sum(
                    parameter.kind in (
                        parameter.POSITIONAL_ONLY,
                        parameter.POSITIONAL_OR_KEYWORD,
                    )
                    for parameter in parameters
                )

    @staticmethod
    def _store(value):
        owner = getattr(value, "__self__", None)
        name = getattr(value, "__name__", None)
        if owner is None or name is None:
            return value
        try:
            return ref(owner), name
        except TypeError:
            return value

    @staticmethod
    def _resolve(value):
        if not (
            isinstance(value, tuple)
            and len(value) == 2
            and isinstance(value[1], str)
            and callable(value[0])
        ):
            return value
        owner = value[0]()
        if owner is None:
            return None
        return getattr(owner, value[1], None)

    def __call__(self, *args, **kwargs):
        try:
            stored = self._callable
        except AttributeError:
            # Emitted into while this adapter is itself being finalised.
            # A connection Qt must keep -- ``destroyed`` is the one that
            # tells a host its dock has gone -- still fires during
            # teardown, by which time this object's own state may be
            # cleared. There is nothing left to call, and raising here
            # only produces unraisable noise at exit.
            return None
        callback = self._resolve(stored)
        if callback is None:
            return None
        stored_args = []
        for value in self._args:
            resolved = self._resolve(value)
            if resolved is None and resolved is not value:
                return None
            stored_args.append(resolved)
        stored_keywords = {}
        for key, value in self._keywords.items():
            resolved = self._resolve(value)
            if resolved is None and resolved is not value:
                return None
            stored_keywords[key] = resolved
        if self._positional_limit is not None:
            args = args[:self._positional_limit]
        if self._partial:
            return callback(
                *stored_args,
                *args,
                **stored_keywords,
                **kwargs
            )
        return callback(*args, **kwargs)


def weak_callback(callback):
    """Return a callback that does not retain a bound receiver.

    Use this for a sender whose Qt lifetime is shorter than the component
    receiving it.  The sender owns the adapter, and no Python registry keeps
    a signal wrapper after the sender's native object has gone away.
    """
    return _WeakCallable(callback)


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

    def connect_weak(self, signal, slot, connection_type=None):
        """Connect while keeping a bound receiver outside signal ownership."""
        weak_slot = weak_callback(slot)
        self.connect(signal, weak_slot, connection_type)
        return weak_slot

    def disconnect_all(self):
        for signal, slot in reversed(self._connections):
            try:
                signal.disconnect(slot)
            except (RuntimeError, TypeError):
                # A Qt owner may already have destroyed the underlying object.
                pass
        self._connections.clear()
