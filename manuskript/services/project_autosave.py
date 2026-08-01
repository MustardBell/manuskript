from PyQt5.QtCore import QTimer


class ProjectAutosaveScheduler:
    """Own the Qt timers used by project autosave policy."""

    def __init__(self, save_callback, timer_factory=QTimer):
        self._periodic_timer = timer_factory()
        self._after_change_timer = timer_factory()
        self._after_change_enabled = False

        self._periodic_timer.timeout.connect(save_callback)
        self._after_change_timer.timeout.connect(save_callback)
        self._periodic_timer.setSingleShot(False)
        self._after_change_timer.setSingleShot(True)

    def configure(
        self,
        *,
        periodic_enabled,
        periodic_delay_minutes,
        after_change_enabled,
        after_change_delay_seconds,
    ):
        self._periodic_timer.stop()
        self._after_change_timer.stop()
        self._periodic_timer.setInterval(
            periodic_delay_minutes * 60 * 1000
        )
        self._after_change_timer.setInterval(
            after_change_delay_seconds * 1000
        )
        self._after_change_enabled = after_change_enabled
        if periodic_enabled:
            self._periodic_timer.start()

    def schedule_after_change(self):
        if self._after_change_enabled:
            self._after_change_timer.start()

    def saving_started(self):
        self._after_change_timer.stop()

    def stop(self):
        self._periodic_timer.stop()
        self._after_change_timer.stop()
