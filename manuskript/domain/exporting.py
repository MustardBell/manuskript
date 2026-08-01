from dataclasses import dataclass
from typing import Union


@dataclass(frozen=True)
class ExportArtifact:
    """A rendered document that can be previewed, saved, or converted."""

    content: Union[str, bytes]
    suggested_name: str
    media_type: str = "application/octet-stream"
