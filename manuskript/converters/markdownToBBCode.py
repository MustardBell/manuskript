import re


_INLINE_CONTENT = r"(?:(?!\r?\n[ \t]*\r?\n).)+?"


def _replace_indented_line(match):
    spaces = len(match.group(1))
    level = min(5, spaces // 4)
    suffix = "={}".format(level) if level > 1 else ""
    return "[indent{}]{}[/indent]".format(suffix, match.group(2))


def markdown_to_bbcode(text):
    """Convert Manuskript Markdown to forum-oriented BBCode."""
    if not isinstance(text, str) or not text:
        return text

    text = re.sub(
        r"\[!\[.*?\]\((.*?)\)\]\((.*?)\)",
        r"[img]\1[/img]\nClickable image was pointing to "
        r"[url=\2]here[/url]",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    text = re.sub(
        r"!\[(.*?)\]\((.*?)\)",
        r"[img]\2[/img]",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    text = re.sub(
        r"(?<!!)\[(.+?)\]\((.+?)(?:\s+\".*?\")?\)",
        r"[url=\2]\1[/url]",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    text = re.sub(
        r"^(.+)\r?\n={3}\s*$",
        r"[h1]\1[/h1]",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    text = re.sub(
        r"^(.+)\r?\n-{3}\s*$",
        r"[h2]\1[/h2]",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    text = re.sub(
        r"~(.+?)~",
        r"[u][size=1]\1[/size][/u]",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    for level in range(6, 0, -1):
        text = re.sub(
            r"^#{%d}\s*(.*?)\s*#*\s*$" % level,
            r"[h%d]\1[/h%d]" % (level, level),
            text,
            flags=re.IGNORECASE | re.MULTILINE,
        )
    text = re.sub(
        r"^>\s?(.*)$",
        r"\1",
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )
    text = re.sub(
        r"^( {4,20})(\S.*)$",
        _replace_indented_line,
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    for source, target in (
        ("=>", "►"),
        ("<=", "◄"),
        ("<->", "↔"),
    ):
        text = text.replace(source, target)
    text = re.sub(
        r"\*\*\s*->\s*\*\*",
        "[size=6]→[/size]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"\*\*\s*<-\s*\*\*",
        "[size=6]←[/size]",
        text,
        flags=re.IGNORECASE,
    )
    text = text.replace("->", "→").replace("<-", "←")

    text = re.sub(
        r"^```[^\n]*\n(.*?)\n```\s*$",
        r"[code]\1[/code]",
        text,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    text = re.sub(
        r"^~~~[^\n]*\n(.*?)\n~~~\s*$",
        r"[code]\1[/code]",
        text,
        flags=re.IGNORECASE | re.MULTILINE | re.DOTALL,
    )
    text = re.sub(
        r"`([^`\n]+)`",
        r"[code single]\1[/code]",
        text,
        flags=re.IGNORECASE,
    )
    text = re.sub(
        r"(?<!\*)\*\*(?!\s)(" + _INLINE_CONTENT + r")(?<!\s)\*\*",
        r"[b]\1[/b]",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"(?<!\*)\*(?!\*|\s)(" + _INLINE_CONTENT
        + r")(?<!\s|\*)\*(?!\*)",
        r"[i]\1[/i]",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    text = re.sub(
        r"(?<=[\w,!?'\" ])--(?=[ \w,!?'\"])",
        "—",
        text,
    )
    return text.replace(" - ", "—")
