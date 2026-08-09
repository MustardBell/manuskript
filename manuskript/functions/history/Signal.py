
class Signal:
    def __init__(self) -> None:
        self._methods = []

    def connect(self, func):
        self._methods.append(func)

    def disconnect(self, func=None):
        """Disconnect ``func``, or the latest listener for compatibility.

        The class previously declared this method twice.  The no-argument
        declaration replaced the callback form at import time, so an owner
        could not release its own subscription and instead had to remove
        whichever listener happened to register last.
        """
        if func is None:
            if not self._methods:
                raise TypeError
            self._methods.pop()
            return
        try:
            self._methods.remove(func)
        except ValueError as error:
            raise TypeError from error

    def fire(self, data):
        # A callback may disconnect itself. Iterating a snapshot ensures that
        # doing so does not skip the listener that followed it.
        for method in tuple(self._methods):
            method(data)
