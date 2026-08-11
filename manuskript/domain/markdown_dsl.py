"""Source-preserving parsing for Manuskript's generic Markdown DSL."""

import re
from dataclasses import dataclass
from typing import Any, Iterable, List, Mapping, Optional, Tuple


@dataclass(frozen=True, order=True)
class SourceSpan:
    start: int
    end: int

    def __post_init__(self):
        if self.start < 0 or self.end < self.start:
            raise ValueError("Invalid source span: {}..{}".format(
                self.start, self.end
            ))

    @property
    def length(self) -> int:
        return self.end - self.start

    def extract(self, source: str) -> str:
        return source[self.start:self.end]


@dataclass(frozen=True)
class DslDiagnostic:
    message: str
    span: SourceSpan
    severity: str = "warning"


@dataclass(frozen=True)
class Wikilink:
    span: SourceSpan
    target_span: SourceSpan
    display_span: Optional[SourceSpan]
    target: str
    display: Optional[str]
    embedded: bool = False

    @property
    def rendered_text(self) -> str:
        return self.display if self.display is not None else self.target


@dataclass(frozen=True)
class MarkdownDslNode:
    """A generic syntax node contributed by a Markdown DSL extension."""

    kind: str
    span: SourceSpan
    attributes: Tuple[Tuple[str, Any], ...] = ()

    @classmethod
    def from_mapping(
        cls,
        kind: str,
        span: SourceSpan,
        attributes: Optional[Mapping[str, Any]] = None,
    ):
        return cls(kind, span, tuple((attributes or {}).items()))


@dataclass(frozen=True)
class MarkdownDslExtensionResult:
    """Source-bound output returned by a parser extension."""

    nodes: Tuple[MarkdownDslNode, ...] = ()
    diagnostics: Tuple[DslDiagnostic, ...] = ()


@dataclass(frozen=True)
class MarkdownSyntaxTree:
    source: str
    wikilinks: Tuple[Wikilink, ...] = ()
    nodes: Tuple[MarkdownDslNode, ...] = ()
    diagnostics: Tuple[DslDiagnostic, ...] = ()

    def replace(self, replacements: Iterable[Tuple[SourceSpan, str]]) -> str:
        """Apply non-overlapping source edits without reparsing other text."""

        ordered = sorted(replacements, key=lambda item: item[0].start)
        previous_end = -1
        for span, _text in ordered:
            if span.start < previous_end:
                raise ValueError("Source-preserving edits may not overlap.")
            previous_end = span.end
        result = self.source
        for span, text in reversed(ordered):
            result = result[:span.start] + text + result[span.end:]
        return result


class MarkdownDslParser:
    """Parse generic DSL constructs while treating malformed text as prose."""

    _FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")

    def __init__(self, extensions=()):
        """Create a parser with optional, fiction-agnostic syntax extensions.

        Each extension implements ``parse(source, excluded_spans)`` and
        returns :class:`MarkdownDslExtensionResult`. An extension failure is
        recovered as a diagnostic, leaving the source untouched.
        """

        self._extensions = tuple(extensions)

    def parse(self, source: str) -> MarkdownSyntaxTree:
        excluded = self.excluded_spans(source)
        links: List[Wikilink] = []
        diagnostics: List[DslDiagnostic] = []
        position = 0
        length = len(source)

        while position < length:
            opening = source.find("[[", position)
            if opening < 0:
                break
            if self._escaped(source, opening) or self._inside(opening, excluded):
                position = opening + 2
                continue
            closing = source.find("]]", opening + 2)
            if closing < 0 or "\n" in source[opening + 2:closing]:
                diagnostics.append(DslDiagnostic(
                    "Unclosed wikilink; the source remains ordinary Markdown.",
                    SourceSpan(opening, min(length, opening + 2)),
                ))
                position = opening + 2
                continue
            if self._inside(closing, excluded):
                position = closing + 2
                continue

            payload_start = opening + 2
            payload = source[payload_start:closing]
            separator = payload.find("|")
            if separator < 0:
                raw_target = payload
                raw_display = None
                display_span = None
            else:
                raw_target = payload[:separator]
                raw_display = payload[separator + 1:]
                display_span = SourceSpan(
                    payload_start + separator + 1, closing
                )
            target = raw_target.strip()
            display = raw_display.strip() if raw_display is not None else None
            if not target:
                diagnostics.append(DslDiagnostic(
                    "A wikilink target may not be empty.",
                    SourceSpan(opening, closing + 2),
                    "error",
                ))
                position = closing + 2
                continue
            if display is not None and not display:
                diagnostics.append(DslDiagnostic(
                    "An empty wikilink display falls back to the target.",
                    display_span,
                ))
                display = None
                display_span = None

            left_trim = len(raw_target) - len(raw_target.lstrip())
            right_trim = len(raw_target) - len(raw_target.rstrip())
            links.append(Wikilink(
                span=SourceSpan(
                    opening - 1
                    if opening > 0 and source[opening - 1] == "!"
                    and not self._escaped(source, opening - 1)
                    else opening,
                    closing + 2,
                ),
                target_span=SourceSpan(
                    payload_start + left_trim,
                    payload_start + len(raw_target) - right_trim,
                ),
                display_span=display_span,
                target=target,
                display=display,
                embedded=(
                    opening > 0 and source[opening - 1] == "!"
                    and not self._escaped(source, opening - 1)
                ),
            ))
            position = closing + 2

        nodes = []
        for extension in self._extensions:
            try:
                result = extension.parse(source, excluded)
                if not isinstance(result, MarkdownDslExtensionResult):
                    raise TypeError(
                        "Markdown DSL extensions must return "
                        "MarkdownDslExtensionResult."
                    )
                nodes.extend(result.nodes)
                diagnostics.extend(result.diagnostics)
            except Exception as error:
                diagnostics.append(DslDiagnostic(
                    "Markdown DSL extension {} failed: {}".format(
                        type(extension).__name__, error
                    ),
                    SourceSpan(0, 0),
                    "error",
                ))

        return MarkdownSyntaxTree(
            source,
            tuple(links),
            tuple(nodes),
            tuple(diagnostics),
        )

    def excluded_spans(self, source: str) -> Tuple[SourceSpan, ...]:
        """Return Markdown code ranges in which DSL syntax is literal."""

        return self._code_spans(source)

    def update(
        self,
        tree: MarkdownSyntaxTree,
        span: SourceSpan,
        replacement: str,
    ) -> MarkdownSyntaxTree:
        """Incrementally reparse an edited line when that is provably safe.

        Wikilinks and inline code cannot cross a line. Therefore an edit in a
        document without fenced blocks or parser extensions only invalidates
        the lines it touches. Fences and extensions deliberately fall back to
        a full parse; correctness takes precedence over an optimistic cache.
        """

        if span.end > len(tree.source):
            raise ValueError("The edit span extends beyond the source.")
        new_source = tree.replace(((span, replacement),))
        if self._extensions or any(
            self._FENCE.match(line) for line in tree.source.splitlines()
        ):
            return self.parse(new_source)

        old_start = tree.source.rfind("\n", 0, span.start) + 1
        old_end = tree.source.find("\n", span.end)
        old_end = len(tree.source) if old_end < 0 else old_end + 1
        new_edit_end = span.start + len(replacement)
        new_end = new_source.find("\n", new_edit_end)
        new_end = len(new_source) if new_end < 0 else new_end + 1
        delta = len(new_source) - len(tree.source)

        fragment = self.parse(new_source[old_start:new_end])
        links = [
            link for link in tree.wikilinks if link.span.end <= old_start
        ]
        links.extend(
            self._shift_wikilink(link, old_start)
            for link in fragment.wikilinks
        )
        links.extend(
            self._shift_wikilink(link, delta)
            for link in tree.wikilinks if link.span.start >= old_end
        )
        diagnostics = [
            item for item in tree.diagnostics if item.span.end <= old_start
        ]
        diagnostics.extend(
            self._shift_diagnostic(item, old_start)
            for item in fragment.diagnostics
        )
        diagnostics.extend(
            self._shift_diagnostic(item, delta)
            for item in tree.diagnostics if item.span.start >= old_end
        )
        return MarkdownSyntaxTree(
            new_source,
            tuple(sorted(links, key=lambda item: item.span.start)),
            (),
            tuple(sorted(diagnostics, key=lambda item: item.span.start)),
        )

    @staticmethod
    def _shift_span(span: Optional[SourceSpan], offset: int):
        if span is None:
            return None
        return SourceSpan(span.start + offset, span.end + offset)

    @classmethod
    def _shift_wikilink(cls, link: Wikilink, offset: int) -> Wikilink:
        return Wikilink(
            cls._shift_span(link.span, offset),
            cls._shift_span(link.target_span, offset),
            cls._shift_span(link.display_span, offset),
            link.target,
            link.display,
            link.embedded,
        )

    @classmethod
    def _shift_diagnostic(
        cls, diagnostic: DslDiagnostic, offset: int
    ) -> DslDiagnostic:
        return DslDiagnostic(
            diagnostic.message,
            cls._shift_span(diagnostic.span, offset),
            diagnostic.severity,
        )

    def _code_spans(self, source: str) -> Tuple[SourceSpan, ...]:
        spans = []
        offset = 0
        fence_marker = None
        fence_start = None
        for line in source.splitlines(keepends=True):
            match = self._FENCE.match(line)
            if match:
                marker = match.group(1)
                if fence_marker is None:
                    fence_marker = marker
                    fence_start = offset
                elif marker[0] == fence_marker[0] and len(marker) >= len(fence_marker):
                    spans.append(SourceSpan(fence_start, offset + len(line)))
                    fence_marker = None
                    fence_start = None
            elif fence_marker is None:
                spans.extend(self._inline_code_spans(line, offset))
            offset += len(line)
        if fence_start is not None:
            spans.append(SourceSpan(fence_start, len(source)))
        return tuple(spans)

    @staticmethod
    def _inline_code_spans(line: str, offset: int) -> List[SourceSpan]:
        spans = []
        position = 0
        while position < len(line):
            opening = line.find("`", position)
            if opening < 0:
                break
            run = 1
            while opening + run < len(line) and line[opening + run] == "`":
                run += 1
            closing = line.find("`" * run, opening + run)
            if closing < 0:
                break
            spans.append(SourceSpan(
                offset + opening, offset + closing + run
            ))
            position = closing + run
        return spans

    @staticmethod
    def _inside(position: int, spans: Tuple[SourceSpan, ...]) -> bool:
        return any(span.start <= position < span.end for span in spans)

    @staticmethod
    def _escaped(source: str, position: int) -> bool:
        slashes = 0
        position -= 1
        while position >= 0 and source[position] == "\\":
            slashes += 1
            position -= 1
        return bool(slashes % 2)


def render_wikilinks_as_markdown(source: str) -> str:
    """Project wikilinks into ordinary Markdown for read-only renderers."""

    tree = MarkdownDslParser().parse(source)
    replacements = []
    for link in tree.wikilinks:
        display = link.rendered_text.replace("]", "\\]")
        target = link.target.replace(" ", "%20").replace(")", "%29")
        prefix = "!" if link.embedded else ""
        replacements.append((
            link.span,
            "{}[{}](manuskript:{})".format(prefix, display, target),
        ))
    return tree.replace(replacements)
