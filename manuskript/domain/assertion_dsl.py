"""Source-preserving fenced Markdown representation of story assertions."""

import re
from dataclasses import replace
from typing import Mapping

import yaml

from manuskript.domain.markdown_dsl import (
    DslDiagnostic,
    MarkdownDslParser,
    MarkdownDslExtensionResult,
    MarkdownDslNode,
    SourceSpan,
    render_wikilinks_as_markdown,
)
from manuskript.domain.story_assertions import (
    Assertion,
    AssertionProvenance,
    AssertionQualifier,
    AssertionTerm,
    CanonState,
    StoryReference,
)


ASSERTION_NODE_KIND = "story-assertion"


class AssertionDslExtension:
    """Parse only explicit ``manuskript-assertion`` fenced blocks."""

    _BLOCK = re.compile(
        r"(?ms)^[ ]{0,3}(?P<fence>`{3,})manuskript-assertion[ \t]*\r?\n"
        r"(?P<body>.*?)^[ ]{0,3}(?P=fence)[ \t]*(?:\r?\n|$)"
    )

    def parse(self, source, _excluded_spans=()):
        excluded_spans = (
            tuple(_excluded_spans)
            if _excluded_spans
            else MarkdownDslParser().excluded_spans(source)
        )
        nodes = []
        diagnostics = []
        for match in self._BLOCK.finditer(source):
            if any(
                excluded.start < match.start() < excluded.end
                for excluded in excluded_spans
            ):
                continue
            span = SourceSpan(match.start(), match.end())
            try:
                value = yaml.safe_load(match.group("body"))
                assertion = decode_assertion(value, span)
            except (TypeError, ValueError, yaml.YAMLError) as error:
                diagnostics.append(DslDiagnostic(
                    "Invalid story assertion: {}".format(error),
                    span,
                    "error",
                ))
                continue
            nodes.append(MarkdownDslNode.from_mapping(
                ASSERTION_NODE_KIND,
                span,
                {"assertion": assertion},
            ))
        return MarkdownDslExtensionResult(
            tuple(nodes), tuple(diagnostics)
        )


def decode_assertion(value, span=None):
    if not isinstance(value, Mapping):
        raise TypeError("the fenced body must be a YAML mapping")
    identifier = str(value.get("id", "")).strip()
    predicate = str(value.get("predicate", "")).strip()
    subject = _decode_reference(value.get("subject"), "subject")
    raw_object = value.get("object")
    if not isinstance(raw_object, Mapping):
        raise TypeError("object must be a mapping")
    if "reference" in raw_object and "value" in raw_object:
        raise ValueError("object must contain reference or value, not both")
    if "reference" in raw_object:
        reference = _decode_reference(raw_object["reference"], "object.reference")
        term = AssertionTerm.referencing(reference.kind, reference.id)
    elif "value" in raw_object:
        term = AssertionTerm.scalar(raw_object["value"])
    else:
        raise ValueError("object must contain reference or value")

    raw_qualifiers = value.get("qualifiers", {})
    if not isinstance(raw_qualifiers, Mapping):
        raise TypeError("qualifiers must be a mapping")
    raw_provenance = value.get("provenance", {})
    if not isinstance(raw_provenance, Mapping):
        raise TypeError("provenance must be a mapping")
    try:
        canon = CanonState(str(value.get("canon", "canon")))
    except ValueError as error:
        raise ValueError("unknown canon state") from error
    return Assertion(
        id=identifier,
        subject=subject,
        predicate=predicate,
        object=term,
        qualifiers=tuple(
            AssertionQualifier(str(name), item)
            for name, item in raw_qualifiers.items()
        ),
        provenance=AssertionProvenance(
            anchor=str(raw_provenance.get("anchor", "")),
            note=str(raw_provenance.get("note", "")),
            source_span=span,
        ),
        canon_state=canon,
    )


def encode_assertion_block(assertion: Assertion) -> str:
    """Serialize one assertion without persisting its derived source span."""

    value = {
        "id": assertion.id,
        "subject": _encode_reference(assertion.subject),
        "predicate": assertion.predicate,
        "object": (
            {"reference": _encode_reference(assertion.object.reference)}
            if assertion.object.reference is not None
            else {"value": assertion.object.value}
        ),
        "qualifiers": {
            item.name: item.value for item in assertion.qualifiers
        },
        "canon": assertion.canon_state.value,
        "provenance": {
            key: item for key, item in (
                ("anchor", assertion.provenance.anchor),
                ("note", assertion.provenance.note),
            ) if item
        },
    }
    body = yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    return "```manuskript-assertion\n{}```\n".format(body)


def assertions_from_source(source):
    result = AssertionDslExtension().parse(source)
    return (
        tuple(node.attribute("assertion") for node in result.nodes),
        result.diagnostics,
    )


def strip_assertion_blocks(source):
    """Remove semantic blocks from an ordinary prose/export projection."""

    result = AssertionDslExtension().parse(source)
    replacements = tuple((node.span, "") for node in result.nodes)
    rendered = source
    for span, value in reversed(replacements):
        rendered = rendered[:span.start] + value + rendered[span.end:]
    return rendered


def render_story_markdown(source):
    return render_wikilinks_as_markdown(strip_assertion_blocks(source))


def bind_assertion_to_document(assertion, document_id):
    return replace(
        assertion,
        provenance=replace(
            assertion.provenance,
            document_id=str(document_id),
        ),
    )


def _decode_reference(value, field):
    if not isinstance(value, Mapping):
        raise TypeError("{} must be a mapping".format(field))
    return StoryReference(
        str(value.get("kind", "")).strip(),
        str(value.get("id", "")).strip(),
    )


def _encode_reference(reference):
    return {"kind": reference.kind, "id": reference.id}
