from functools import wraps

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QCursor
from PyQt5.QtWidgets import qApp


def busy_cursor(function):
    """Decorate a synchronous UI operation with a wait cursor."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        qApp.setOverrideCursor(QCursor(Qt.WaitCursor))
        try:
            return function(*args, **kwargs)
        finally:
            qApp.restoreOverrideCursor()

    return wrapped
