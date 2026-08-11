"""Source-preserving MultiMarkdown metadata parsing used by project codecs."""

import re
from dataclasses import dataclass
from typing import Iterable, Tuple

from manuskript.domain.canonical_project import MetadataField


@dataclass(frozen=True)
class MmdDocument:
    metadata: Tuple[MetadataField, ...]
    body: str

    def value(self, name: str, default: str = "") -> str:
        for field in reversed(self.metadata):
            if field.name == name:
                return field.value
        return default


def parse_mmd(text: str) -> MmdDocument:
    """Parse the historical Manuskript MMD dialect without losing duplicates."""

    metadata = []
    body = []
    description = ""
    value = ""
    in_body = False

    for line in text.split("\n"):
        # Keep the source-preserving codec's raw text untouched while parsing
        # CRLF input into the same semantic model as LF input.  split("\n")
        # is intentional here: unlike splitlines(), it retains terminal empty
        # lines, which are meaningful to the historical MMD body parser.
        if line.endswith("\r"):
            line = line[:-1]
        if in_body:
            body.append(line)
            continue

        match = re.match(r"^([^\s].*?):\s*(.*)$", line)
        if match:
            if description:
                metadata.append(MetadataField(
                    "" if description == "None" else description,
                    value,
                ))
            description = match.group(1)
            value = match.group(2)
        elif line.startswith("    "):
            value += "\n" + line.strip()
        elif line == "":
            in_body = True
            if description:
                metadata.append(MetadataField(
                    "" if description == "None" else description,
                    value,
                ))

    if body and body[0] == "":
        body = body[1:]
    return MmdDocument(tuple(metadata), "\n".join(body))


def format_metadata(field: MetadataField, tab_length: int = 15) -> str:
    name = (field.name or "None").replace(":", "_.._")
    value = str(field.value)
    if "\n" in value:
        value = "\n".join(
            " " * (tab_length + 1) + line
            for line in value.split("\n")
        )[tab_length + 1:]
    return "{name}:{spaces}{value}\n".format(
        name=name,
        spaces=" " * max(1, tab_length - len(name)),
        value=value,
    )


def encode_mmd(
    metadata: Iterable[MetadataField],
    body: str = "",
    tab_length: int = 15,
) -> str:
    header = "".join(
        format_metadata(field, tab_length=tab_length)
        for field in metadata
    )
    return header + "\n\n" + body
