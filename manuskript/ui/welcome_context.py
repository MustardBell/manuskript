from dataclasses import dataclass
from typing import Callable

from manuskript.services.project_templates import (
    ProjectTemplateInitializer,
    ProjectTemplateModels,
)


@dataclass(frozen=True)
class WelcomeContext:
    project_manager: object
    recent_menu: object
    consume_auto_load_project: Callable
    set_window_title: Callable[[str], None]
    template_initializer: ProjectTemplateInitializer


def welcome_context_for(window, settings):
    def current_template_models():
        return ProjectTemplateModels(
            flat_data=window.mdlFlatData,
            labels=window.mdlLabels,
            statuses=window.mdlStatus,
            outline=window.mdlOutline,
        )

    return WelcomeContext(
        project_manager=window.projectManager,
        recent_menu=window.menuRecents,
        consume_auto_load_project=window.consumeAutoLoadProject,
        set_window_title=window.setWindowTitle,
        template_initializer=ProjectTemplateInitializer(
            settings,
            window.projectManager.loadEmptyDatas,
            current_template_models,
        ),
    )
