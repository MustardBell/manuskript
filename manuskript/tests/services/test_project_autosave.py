from unittest.mock import MagicMock

from manuskript.services.project_autosave import (
    ProjectAutosaveScheduler,
)


def make_scheduler():
    periodic_timer = MagicMock()
    after_change_timer = MagicMock()
    timers = iter((periodic_timer, after_change_timer))
    save = MagicMock()
    scheduler = ProjectAutosaveScheduler(
        save,
        timer_factory=lambda: next(timers),
    )
    return scheduler, save, periodic_timer, after_change_timer


def test_scheduler_configures_periodic_and_idle_timers():
    scheduler, _, periodic, after_change = make_scheduler()

    scheduler.configure(
        periodic_enabled=True,
        periodic_delay_minutes=15,
        after_change_enabled=True,
        after_change_delay_seconds=3,
    )

    periodic.setInterval.assert_called_once_with(15 * 60 * 1000)
    periodic.start.assert_called_once_with()
    after_change.setInterval.assert_called_once_with(3 * 1000)

    scheduler.schedule_after_change()
    after_change.start.assert_called_once_with()


def test_scheduler_disables_timers_and_stops_pending_work():
    scheduler, _, periodic, after_change = make_scheduler()

    scheduler.configure(
        periodic_enabled=False,
        periodic_delay_minutes=5,
        after_change_enabled=False,
        after_change_delay_seconds=2,
    )
    scheduler.schedule_after_change()
    scheduler.saving_started()
    scheduler.stop()

    periodic.start.assert_not_called()
    after_change.start.assert_not_called()
    assert periodic.stop.call_count == 2
    assert after_change.stop.call_count == 3


def test_each_timer_invokes_the_save_callback():
    _, save, periodic, after_change = make_scheduler()

    periodic.timeout.connect.call_args.args[0]()
    after_change.timeout.connect.call_args.args[0]()

    assert save.call_count == 2
