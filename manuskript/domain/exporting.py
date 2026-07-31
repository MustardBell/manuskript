from dataclasses import dataclass


@dataclass(frozen=True)
class ExportArtifact:
    """A rendered document that can be previewed, saved, or converted."""

    content: str | bytes
    suggested_name: str
    media_type: str = "application/octet-stream"
