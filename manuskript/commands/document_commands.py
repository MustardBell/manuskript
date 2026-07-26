from enum import Enum


class DocumentCommand(str, Enum):
    COPY = "copy"
    CUT = "cut"
    PASTE = "paste"
    RENAME = "rename"
    DUPLICATE = "duplicate"
    DELETE = "delete"
    MOVE_UP = "moveUp"
    MOVE_DOWN = "moveDown"
    SPLIT_DIALOG = "splitDialog"
    SPLIT_CURSOR = "splitCursor"
    MERGE = "merge"


class DocumentCommandRouter:
    """Dispatch document commands to the active view's capable endpoint."""

    def __init__(self, target_provider):
        self._target_provider = target_provider

    def can_dispatch(self, command):
        command = DocumentCommand(command)
        target = self._resolve_target(command)
        return callable(getattr(target, command.value, None))

    def dispatch(self, command, *_signal_args):
        command = DocumentCommand(command)
        target = self._resolve_target(command)
        handler = getattr(target, command.value, None)
        if not callable(handler):
            return False
        handler()
        return True

    def _resolve_target(self, command):
        target = self._target_provider()
        visited = set()

        while target is not None and id(target) not in visited:
            visited.add(id(target))
            resolver = getattr(target, "document_command_target", None)
            if not callable(resolver):
                break
            resolved = resolver(command)
            if resolved is target:
                break
            target = resolved

        return target
