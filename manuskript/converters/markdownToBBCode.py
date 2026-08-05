"""Markdown to forum BBCode conversion, as an ordered list of rules.

The passes have no shared state, so they are expressed as data rather than a
sequence of statements. That lets a plugin add its own rules to a private
copy of the converter without reaching into this module and without changing
what core produces for anyone else.

Order matters throughout. ``** -> **`` has to be matched before the bare
``->`` literal, and headings before blockquote stripping.
"""

import re
from dataclasses import dataclass
from typing import Union


_INLINE_CONTENT = r"(?:(?!\r?\n[ \t]*\r?\n).)+?"


def _replace_indented_line(match):
    spaces = len(match.group(1))
    level = min(5, spaces // 4)
    suffix = "={}".format(level) if level > 1 else ""
    return "[indent{}]{}[/indent]".format(suffix, match.group(2))


@dataclass(frozen=True)
class MarkupRule:
    """One conversion pass.

    ``literal`` rules are plain string replacement; the rest are regular
    expressions whose ``replacement`` may be a template or a callable.
    """

    pattern: str
    replacement: Union[str, object]
    flags: int = 0
    literal: bool = False

    def apply(self, text):
        if self.literal:
            return text.replace(self.pattern, self.replacement)
        return re.sub(
            self.pattern,
            self.replacement,
            text,
            flags=self.flags,
        )


def _heading_rules():
    """Deepest first, so ###### is not eaten by the # rule."""
    return tuple(
        MarkupRule(
            r"^#{%d}\s*(.*?)\s*#*\s*$" % level,
            r"[h%d]\1[/h%d]" % (level, level),
            re.IGNORECASE | re.MULTILINE,
        )
        for level in range(6, 0, -1)
    )


BBCODE_RULES = (
    MarkupRule(
        r"\[!\[.*?\]\((.*?)\)\]\((.*?)\)",
        r"[img]\1[/img]\nClickable image was pointing to "
        r"[url=\2]here[/url]",
        re.IGNORECASE | re.MULTILINE,
    ),
    MarkupRule(
        r"!\[(.*?)\]\((.*?)\)",
        r"[img]\2[/img]",
        re.IGNORECASE | re.MULTILINE,
    ),
    MarkupRule(
        r"(?<!!)\[(.+?)\]\((.+?)(?:\s+\".*?\")?\)",
        r"[url=\2]\1[/url]",
        re.IGNORECASE | re.MULTILINE,
    ),
    MarkupRule(
        r"^(.+)\r?\n={3}\s*$",
        r"[h1]\1[/h1]",
        re.IGNORECASE | re.MULTILINE,
    ),
    MarkupRule(
        r"^(.+)\r?\n-{3}\s*$",
        r"[h2]\1[/h2]",
        re.IGNORECASE | re.MULTILINE,
    ),
    MarkupRule(
        r"~(.+?)~",
        r"[u][size=1]\1[/size][/u]",
        re.IGNORECASE | re.DOTALL,
    ),
) + _heading_rules() + (
    MarkupRule(
        r"^>\s?(.*)$",
        r"\1",
        re.IGNORECASE | re.MULTILINE,
    ),
    MarkupRule(
        r"^( {4,20})(\S.*)$",
        _replace_indented_line,
        re.IGNORECASE | re.MULTILINE,
    ),
    MarkupRule("=>", "►", literal=True),
    MarkupRule("<=", "◄", literal=True),
    MarkupRule("<->", "↔", literal=True),
    MarkupRule(
        r"\*\*\s*->\s*\*\*",
        "[size=6]→[/size]",
        re.IGNORECASE,
    ),
    MarkupRule(
        r"\*\*\s*<-\s*\*\*",
        "[size=6]←[/size]",
        re.IGNORECASE,
    ),
    MarkupRule("->", "→", literal=True),
    MarkupRule("<-", "←", literal=True),
    MarkupRule(
        r"^```[^\n]*\n(.*?)\n```\s*$",
        r"[code]\1[/code]",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    ),
    MarkupRule(
        r"^~~~[^\n]*\n(.*?)\n~~~\s*$",
        r"[code]\1[/code]",
        re.IGNORECASE | re.MULTILINE | re.DOTALL,
    ),
    MarkupRule(
        r"`([^`\n]+)`",
        r"[code single]\1[/code]",
        re.IGNORECASE,
    ),
    MarkupRule(
        r"(?<!\*)\*\*(?!\s)(" + _INLINE_CONTENT + r")(?<!\s)\*\*",
        r"[b]\1[/b]",
        re.IGNORECASE | re.DOTALL,
    ),
    MarkupRule(
        r"(?<!\*)\*(?!\*|\s)(" + _INLINE_CONTENT
        + r")(?<!\s|\*)\*(?!\*)",
        r"[i]\1[/i]",
        re.IGNORECASE | re.DOTALL,
    ),
    MarkupRule(
        r"(?<=[\w,!?'\" ])--(?=[ \w,!?'\"])",
        "—",
    ),
    MarkupRule(" - ", "—", literal=True),
)


class BBCodeConverter:
    """Apply the BBCode rules in order.

    Instances are cheap and immutable in effect: :meth:`extended` returns a
    new converter rather than mutating this one, so a plugin's extra rules
    stay private to that plugin.
    """

    RULES = BBCODE_RULES

    def __init__(self, rules=None):
        self.rules = tuple(self.RULES if rules is None else rules)

    def convert(self, text):
        if not isinstance(text, str) or not text:
            return text
        for rule in self.rules:
            text = rule.apply(text)
        return text

    def extended(self, *rules):
        """A converter with ``rules`` appended, leaving this one untouched."""
        return type(self)(self.rules + tuple(rules))


def markdown_to_bbcode(text):
    """Convert Manuskript Markdown to forum-oriented BBCode."""
    return BBCodeConverter().convert(text)
