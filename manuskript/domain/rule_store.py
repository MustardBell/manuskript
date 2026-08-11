"""Disposable index of custom rule definitions stored in Markdown."""

from dataclasses import dataclass, replace

from manuskript.domain.markdown_dsl import SourceSpan
from manuskript.domain.rule_dsl import rules_from_source


@dataclass(frozen=True)
class RuleDocument:
    id: str
    path: str
    text: str


@dataclass(frozen=True)
class RuleStoreIssue:
    document_id: str
    path: str
    message: str
    severity: str
    source_span: SourceSpan


class RuleStore:
    def __init__(self):
        self._rules = ()
        self._issues = ()

    @property
    def rules(self):
        return self._rules

    @property
    def issues(self):
        return self._issues

    def rebuild(self, documents=()):
        rules = []
        issues = []
        identifiers = set()
        for document in documents:
            parsed, diagnostics = rules_from_source(document.text)
            issues.extend(
                RuleStoreIssue(
                    document.id,
                    document.path,
                    item.message,
                    item.severity,
                    item.span,
                )
                for item in diagnostics
            )
            for rule in parsed:
                if rule.id in identifiers:
                    issues.append(RuleStoreIssue(
                        document.id,
                        document.path,
                        "Duplicate custom rule ID: {}".format(rule.id),
                        "error",
                        rule.source_span,
                    ))
                    continue
                identifiers.add(rule.id)
                rules.append(replace(rule, id=str(rule.id)))
        self._rules = tuple(rules)
        self._issues = tuple(issues)
        return self._rules
