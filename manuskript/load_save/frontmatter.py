"""Safe YAML frontmatter parsing with untouched-source preservation."""

from dataclasses import dataclass
from typing import Any, Mapping, Tuple

import yaml


@dataclass(frozen=True)
class FrontmatterDocument:
    metadata: Mapping[str, Any]
    body: str
    has_frontmatter: bool


def parse_frontmatter(source: str) -> FrontmatterDocument:
    if not source.startswith("---\n"):
        return FrontmatterDocument({}, source, False)
    lines = source.splitlines(keepends=True)
    closing = None
    for index in range(1, len(lines)):
        if lines[index].rstrip("\r\n") in ("---", "..."):
            closing = index
            break
    if closing is None:
        raise ValueError("YAML frontmatter has no closing delimiter.")
    yaml_source = "".join(lines[1:closing])
    loaded = yaml.safe_load(yaml_source) or {}
    if not isinstance(loaded, dict):
        raise ValueError("YAML frontmatter must contain a mapping.")
    return FrontmatterDocument(
        loaded,
        "".join(lines[closing + 1:]),
        True,
    )


def encode_frontmatter(metadata: Mapping[str, Any], body: str) -> str:
    header = yaml.safe_dump(
        dict(metadata),
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )
    return "---\n{}---\n{}".format(header, body)
