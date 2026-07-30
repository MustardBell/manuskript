import collections
from dataclasses import dataclass, field


def default_revision_settings():
    return {
        "keep": False,
        "backend": "internal",
        "smartremove": True,
        "git": {
            "autoCommit": False,
            "taggedOnly": False,
        },
        "rules": collections.OrderedDict({
            10 * 60: 60,
            60 * 60: 60 * 10,
            60 * 60 * 24: 60 * 60,
            60 * 60 * 24 * 30: 60 * 60 * 24,
            None: 60 * 60 * 24 * 7,
        }),
    }


@dataclass
class DefaultOutlineSettings:
    """Safe editing policy for detached outline models and items."""

    countSpaces: bool = True
    revisions: dict = field(default_factory=default_revision_settings)
