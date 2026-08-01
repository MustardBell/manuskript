from manuskript.functions.history.History import History


class NavigationController:
    """Coordinate history traversal with a navigation view adapter."""

    def __init__(self, view, history=None):
        self.view = view
        self.history = history or History()
        self.history.navigated.connect(self.navigated)

    def back(self):
        self.history.back()

    def forward(self):
        self.history.forward()

    def record(self, entry, *, replace=False):
        if replace:
            self.history.replace(entry)
        else:
            self.history.next(entry)

    def reset(self):
        self.history.reset()

    def navigated(self, event):
        if event.entry:
            self.view.navigate(event.entry)
        self.view.set_history_actions(
            can_go_back=event.position > 0,
            can_go_forward=event.position < event.count - 1,
        )
