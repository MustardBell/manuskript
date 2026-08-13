"""Load the language-neutral Plugin API and RPC protocol documents.

The checked-in JSON documents are the contract.  Python records and runtime
tables bind to them; they do not silently define a second API.
"""

import copy
import json
import sys

from functools import lru_cache
from pathlib import Path


def _specification_root():
    roots = []
    frozen_root = getattr(sys, "_MEIPASS", None)
    if frozen_root:
        roots.append(Path(frozen_root))
    roots.append(Path(__file__).resolve().parents[2])
    for root in roots:
        candidate = root / "plugin_api" / "schema"
        if candidate.is_dir():
            return candidate
    raise RuntimeError(
        "The Manuskript Plugin API specification is missing from this build."
    )


@lru_cache(maxsize=None)
def _load_document(filename):
    path = _specification_root() / filename
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise RuntimeError(
            "Cannot load Plugin API specification {}: {}"
            .format(path, error)
        ) from error
    if not isinstance(value, dict):
        raise RuntimeError(
            "Plugin API specification {} must contain an object."
            .format(path)
        )
    return value


def api_schema_document():
    """Return an isolated copy of the canonical API-1 value schema."""
    return copy.deepcopy(_load_document("api-1.json"))


def manifest_schema_document():
    """Return an isolated copy of the canonical API-1 manifest schema."""
    return copy.deepcopy(_load_document("manifest-1.schema.json"))


def protocol_document():
    """Return an isolated copy of the canonical RPC protocol-1 document."""
    return copy.deepcopy(_load_document("protocol-1.json"))
