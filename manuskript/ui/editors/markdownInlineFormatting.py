#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
from dataclasses import dataclass


_STRONG_PATTERN = re.compile(
    r"\*\*(?=\S).*?\S\*\*(?!\*)|"
    r"__(?=\S).*?\S__(?!_)"
)


@dataclass(frozen=True)
class InlineMarkupEdit:
    """One replacement and the selection to restore after applying it."""

    start: int
    end: int
    replacement: str
    selection_start: int
    selection_end: int


@dataclass(frozen=True)
class _DelimitedSpan:
    start: int
    end: int
    delimiter: str

    @property
    def content_start(self):
        return self.start + len(self.delimiter)

    @property
    def content_end(self):
        return self.end - len(self.delimiter)


def plan_inline_markup_toggle(
    text,
    selection_start,
    selection_end,
    markup,
):
    """Plan a structural Markdown inline-format toggle within one block."""
    start, end = _trim_selection_whitespace(
        text,
        selection_start,
        selection_end,
    )

    if markup == "**":
        spans = _strong_spans(text)
        exact = next(
            (
                span
                for span in spans
                if (
                    span.start == start
                    and span.end == end
                )
            ),
            None,
        )
        if exact is not None:
            return _remove_span(text, exact)

        adjacent = next(
            (
                span
                for span in spans
                if (
                    span.content_start == start
                    and span.content_end == end
                )
            ),
            None,
        )
        if adjacent is not None:
            return _remove_span(text, adjacent)

        enclosing = min(
            (
                span
                for span in spans
                if (
                    span.content_start <= start
                    and end <= span.content_end
                )
            ),
            key=lambda span: span.end - span.start,
            default=None,
        )
        if enclosing is not None:
            return _split_enclosing_span(
                text,
                start,
                end,
                enclosing,
            )

        merge = _merge_neighboring_strong_spans(
            text,
            start,
            end,
            spans,
            markup,
        )
        if merge is not None:
            return merge

    return _toggle_adjacent_or_wrap(
        text,
        start,
        end,
        markup,
    )


def _trim_selection_whitespace(text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while start < end and text[end - 1].isspace():
        end -= 1
    return start, end


def _strong_spans(text):
    return [
        _DelimitedSpan(
            match.start(),
            match.end(),
            match.group(0)[:2],
        )
        for match in _STRONG_PATTERN.finditer(text)
    ]


def _remove_span(text, span):
    content = text[span.content_start:span.content_end]
    return InlineMarkupEdit(
        start=span.start,
        end=span.end,
        replacement=content,
        selection_start=span.start,
        selection_end=span.start + len(content),
    )


def _split_enclosing_span(text, start, end, span):
    prefix = text[span.content_start:start]
    selected = text[start:end]
    suffix = text[end:span.content_end]
    bold_prefix, plain_prefix = _split_left_boundary(prefix)
    plain_suffix, bold_suffix = _split_right_boundary(suffix)

    left = (
        span.delimiter + bold_prefix + span.delimiter
        if bold_prefix
        else ""
    )
    right = (
        span.delimiter + bold_suffix + span.delimiter
        if bold_suffix
        else ""
    )
    replacement = (
        left
        + plain_prefix
        + selected
        + plain_suffix
        + right
    )
    restored_start = (
        span.start
        + len(left)
        + len(plain_prefix)
    )
    return InlineMarkupEdit(
        start=span.start,
        end=span.end,
        replacement=replacement,
        selection_start=restored_start,
        selection_end=restored_start + len(selected),
    )


def _merge_neighboring_strong_spans(
    text,
    start,
    end,
    spans,
    delimiter,
):
    left = max(
        (
            span
            for span in spans
            if (
                span.end <= start
                and _contains_no_word_characters(
                    text[span.end:start]
                )
            )
        ),
        key=lambda span: span.end,
        default=None,
    )
    right = min(
        (
            span
            for span in spans
            if (
                end <= span.start
                and _contains_no_word_characters(
                    text[end:span.start]
                )
            )
        ),
        key=lambda span: span.start,
        default=None,
    )
    if left is None or right is None:
        return None

    merged_delimiter = (
        left.delimiter
        if left.delimiter == right.delimiter
        else delimiter
    )
    left_boundary = text[left.end:start]
    selected = text[start:end]
    right_boundary = text[end:right.start]
    content = (
        text[left.content_start:left.content_end]
        + left_boundary
        + selected
        + right_boundary
        + text[right.content_start:right.content_end]
    )
    replacement = (
        merged_delimiter + content + merged_delimiter
    )
    restored_start = (
        left.start
        + len(merged_delimiter)
        + len(text[left.content_start:left.content_end])
        + len(left_boundary)
    )
    return InlineMarkupEdit(
        start=left.start,
        end=right.end,
        replacement=replacement,
        selection_start=restored_start,
        selection_end=restored_start + len(selected),
    )


def _split_left_boundary(prefix):
    whitespace_start = len(prefix.rstrip())
    if whitespace_start < len(prefix):
        return (
            prefix[:whitespace_start],
            prefix[whitespace_start:],
        )

    boundary_start = len(prefix)
    while (
        boundary_start
        and not _is_word_character(prefix[boundary_start - 1])
    ):
        boundary_start -= 1
    return (
        prefix[:boundary_start],
        prefix[boundary_start:],
    )


def _split_right_boundary(suffix):
    whitespace_end = len(suffix) - len(suffix.lstrip())
    if whitespace_end:
        return (
            suffix[:whitespace_end],
            suffix[whitespace_end:],
        )

    boundary_end = 0
    while (
        boundary_end < len(suffix)
        and not _is_word_character(suffix[boundary_end])
    ):
        boundary_end += 1
    return (
        suffix[:boundary_end],
        suffix[boundary_end:],
    )


def _is_word_character(character):
    return character.isalnum() or character == "_"


def _contains_no_word_characters(text):
    return all(not _is_word_character(character) for character in text)


def _toggle_adjacent_or_wrap(text, start, end, markup):
    markup_length = len(markup)
    selected = text[start:end]
    before = start - markup_length
    after = end + markup_length

    if (
        before >= 0
        and text[before:start] == markup
        and text[end:after] == markup
    ):
        return InlineMarkupEdit(
            start=before,
            end=after,
            replacement=selected,
            selection_start=before,
            selection_end=before + len(selected),
        )

    if (
        selected.startswith(markup)
        and selected.endswith(markup)
        and len(selected) >= 2 * markup_length
    ):
        content = selected[markup_length:-markup_length]
        return InlineMarkupEdit(
            start=start,
            end=end,
            replacement=content,
            selection_start=start,
            selection_end=start + len(content),
        )

    replacement = markup + selected + markup
    restored_start = start + markup_length
    return InlineMarkupEdit(
        start=start,
        end=end,
        replacement=replacement,
        selection_start=restored_start,
        selection_end=restored_start + len(selected),
    )
