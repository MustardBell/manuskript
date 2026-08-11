"""Declarative, source-owned custom continuity rules."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Mapping, Tuple

import yaml

from manuskript.domain.markdown_dsl import (
    DslDiagnostic,
    MarkdownDslParser,
    MarkdownDslExtensionResult,
    MarkdownDslNode,
    SourceSpan,
)


RULE_NODE_KIND = "story-rule"


class CustomRuleKind(str, Enum):
    EXCLUSIVE_OBJECT = "exclusive-object"
    REQUIRES_PRIOR = "requires-prior"


@dataclass(frozen=True)
class CustomRuleDefinition:
    id: str
    label: str
    kind: CustomRuleKind
    predicate: str = ""
    trigger_predicate: str = ""
    required_predicate: str = ""
    scope: str = "subject"
    match: str = "subject-object"
    severity: str = "warning"
    message: str = ""
    source_span: SourceSpan = SourceSpan(0, 0)

    def __post_init__(self):
        object.__setattr__(self, "kind", CustomRuleKind(self.kind))
        if not self.id.strip() or not self.label.strip():
            raise ValueError("Custom rules require stable ID and label.")
        if self.severity not in ("info", "warning", "error"):
            raise ValueError("Rule severity must be info, warning, or error.")
        if self.kind is CustomRuleKind.EXCLUSIVE_OBJECT:
            if not self.predicate.strip():
                raise ValueError("exclusive-object requires predicate")
            if self.scope not in ("subject", "object"):
                raise ValueError("exclusive-object scope is subject or object")
        elif self.kind is CustomRuleKind.REQUIRES_PRIOR:
            if not self.trigger_predicate.strip() or not (
                self.required_predicate.strip()
            ):
                raise ValueError(
                    "requires-prior needs trigger_predicate and "
                    "required_predicate"
                )
            if self.match not in (
                "subject",
                "object",
                "subject-object",
            ):
                raise ValueError(
                    "requires-prior match is subject, object, or subject-object"
                )


class RuleDslExtension:
    """Parse only explicit ``manuskript-rule`` fenced blocks."""

    _BLOCK = re.compile(
        r"(?ms)^[ ]{0,3}(?P<fence>`{3,})manuskript-rule[ \t]*\r?\n"
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
                definition = decode_rule(
                    yaml.safe_load(match.group("body")), span
                )
            except (TypeError, ValueError, yaml.YAMLError) as error:
                diagnostics.append(DslDiagnostic(
                    "Invalid story rule: {}".format(error),
                    span,
                    "error",
                ))
                continue
            nodes.append(MarkdownDslNode.from_mapping(
                RULE_NODE_KIND, span, {"rule": definition}
            ))
        return MarkdownDslExtensionResult(tuple(nodes), tuple(diagnostics))


def decode_rule(value, span=None):
    if not isinstance(value, Mapping):
        raise TypeError("the fenced body must be a YAML mapping")
    try:
        kind = CustomRuleKind(str(value.get("kind", "")))
    except ValueError as error:
        raise ValueError("unknown custom rule kind") from error
    allowed = {
        "id", "label", "kind", "predicate", "trigger_predicate",
        "required_predicate", "scope", "match", "severity", "message",
    }
    unknown = set(value).difference(allowed)
    if unknown:
        raise ValueError(
            "unknown custom rule fields: {}".format(
                ", ".join(sorted(str(item) for item in unknown))
            )
        )
    return CustomRuleDefinition(
        id=str(value.get("id", "")).strip(),
        label=str(value.get("label", "")).strip(),
        kind=kind,
        predicate=str(value.get("predicate", "")).strip(),
        trigger_predicate=str(
            value.get("trigger_predicate", "")
        ).strip(),
        required_predicate=str(
            value.get("required_predicate", "")
        ).strip(),
        scope=str(value.get("scope", "subject")).strip(),
        match=str(value.get("match", "subject-object")).strip(),
        severity=str(value.get("severity", "warning")).strip(),
        message=str(value.get("message", "")).strip(),
        source_span=span or SourceSpan(0, 0),
    )


def encode_rule_block(definition: CustomRuleDefinition):
    value = {
        "id": definition.id,
        "label": definition.label,
        "kind": definition.kind.value,
    }
    for key, item, default in (
        ("predicate", definition.predicate, ""),
        ("trigger_predicate", definition.trigger_predicate, ""),
        ("required_predicate", definition.required_predicate, ""),
        ("scope", definition.scope, "subject"),
        ("match", definition.match, "subject-object"),
        ("severity", definition.severity, "warning"),
        ("message", definition.message, ""),
    ):
        if item != default:
            value[key] = item
    body = yaml.safe_dump(
        value,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
    )
    return "```manuskript-rule\n{}```\n".format(body)


def rules_from_source(source):
    result = RuleDslExtension().parse(source)
    return (
        tuple(node.attribute("rule") for node in result.nodes),
        result.diagnostics,
    )


def strip_rule_blocks(source):
    result = RuleDslExtension().parse(source)
    rendered = source
    for node in reversed(result.nodes):
        rendered = rendered[:node.span.start] + rendered[node.span.end:]
    return rendered
