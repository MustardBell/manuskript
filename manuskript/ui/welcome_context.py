from dataclasses import dataclass
from typing import Callable

from manuskript.services.project_templates import (
    ProjectTemplateInitializer,
    ProjectTemplateModels,
)


@dataclass(frozen=True)
class WelcomeContext:
    project_manager: object
    project_history: object
    recent_menu: object
    consume_auto_load_project: Callable
    set_window_title: Callable[[str], None]
    template_initializer: ProjectTemplateInitializer


def welcome_context_for(window, settings, project_history, runtime):
    """Adapt the window to what the welcome screen needs.

    Takes the project runtime for the models a new project is filled in
    with. Read from it when asked rather than captured, because this is
    built before any project exists and a template fills in whichever
    models the next project brings.
    """
    def current_template_models():
        models = runtime.models
        return ProjectTemplateModels(
            flat_data=models.flat_data,
            labels=models.labels,
            statuses=models.statuses,
            outline=models.outline,
        )

    return WelcomeContext(
        project_manager=window.projectManager,
        project_history=project_history,
        recent_menu=window.menuRecents,
        consume_auto_load_project=window.consumeAutoLoadProject,
        set_window_title=window.setWindowTitle,
        template_initializer=ProjectTemplateInitializer(
            settings,
            window.projectManager.loadEmptyDatas,
            current_template_models,
        ),
    )
