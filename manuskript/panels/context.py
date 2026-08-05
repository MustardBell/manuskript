"""What a panel's widget factory receives.

Deliberately narrow: what a panel genuinely needs is the project's models
and services, not the window it happens to hang in. Until the project
runtime exists as its own object, ``window`` is the escape hatch through
which factories reach both -- every use of it is a coupling the later
stages remove.
"""

from dataclasses import dataclass
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class PanelContext:
    window: Optional[Any] = None
    show_status: Optional[Callable[..., None]] = None
