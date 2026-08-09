from types import SimpleNamespace

from manuskript.domain.writing_session import WritingSessionProgress
from manuskript.enums import Outline
from manuskript.ui.tools.targets import TargetsContext, TargetsDialog


class RootItem:
    def __init__(self, word_count, goal, progress):
        self.values = {
            Outline.wordCount: word_count,
            Outline.goal: goal,
            Outline.goalPercentage: progress,
        }

    def data(self, field):
        return self.values[field]


def test_targets_dialog_reads_explicit_project_and_session_context():
    outline = SimpleNamespace(rootItem=RootItem(50, 100, 0.5))
    session = WritingSessionProgress(start_word_count=20)
    context = TargetsContext(
        outline=lambda: outline,
        writing_session=session,
    )
    dialog = TargetsDialog(context)
    try:
        assert dialog.draft_progress_bar.value() == 50
        assert dialog.session_wc_label.text().replace(",", "") == "30"
        assert not hasattr(dialog, "mw")

        dialog.resetSession()

        assert session.start_word_count == 50
        assert dialog.session_wc_label.text() == "0"
    finally:
        dialog.close()


def test_targets_context_resolves_replaced_project_models():
    first = SimpleNamespace(rootItem=RootItem(10, 20, 0.5))
    second = SimpleNamespace(rootItem=RootItem(30, 60, 0.5))
    runtime = SimpleNamespace(
        models=SimpleNamespace(outline=first),
    )
    context = TargetsContext.for_runtime(
        runtime,
        WritingSessionProgress(),
    )

    assert context.outline() is first

    runtime.models = SimpleNamespace(outline=second)

    assert context.outline() is second


def test_writing_session_progress_owns_its_baseline():
    progress = WritingSessionProgress()

    progress.reset(125)

    assert progress.start_word_count == 125
    assert progress.words_written(150) == 25
