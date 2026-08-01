#!/usr/bin/env python
# -*- coding: utf-8 -*-

import re
from dataclasses import dataclass


_STRONG_PATTERN = re.compile(
    r"\*\*(?=\S).*?\S\*\*(?!\*)|"
    r"__(?=\S).*?\S__(?!_)"
)
_EMPHASIS_PATTERN = re.compile(
    r"(?<!\*)\*(?=\S).*?\S\*(?!\*)|"
    r"(?<!_)_(?=\S).*?\S_(?!_)"
)
_UNDERLINE_PATTERN = re.compile(
    r"<u>(?=\S).*?\S</u>",
    re.IGNORECASE,
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
    opening: str
    closing: str

    @property
    def content_start(self):
        return self.start + len(self.opening)

    @property
    def content_end(self):
        return self.end - len(self.closing)


def plan_inline_markup_toggle(
    text,
    selection_start,
    selection_end,
    opening_markup,
    closing_markup=None,
):
    """Plan a structural Markdown inline-format toggle within one block."""
    closing_markup = closing_markup or opening_markup
    start, end = _trim_selection_whitespace(
        text,
        selection_start,
        selection_end,
    )

    spans = _formatting_spans(
        text,
        opening_markup,
        closing_markup,
    )
    if spans:
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

        merge = _merge_neighboring_formatted_spans(
            text,
            start,
            end,
            spans,
            opening_markup,
            closing_markup,
        )
        if merge is not None:
            return merge

    return _toggle_adjacent_or_wrap(
        text,
        start,
        end,
        opening_markup,
        closing_markup,
    )


def _trim_selection_whitespace(text, start, end):
    while start < end and text[start].isspace():
        start += 1
    while start < end and text[end - 1].isspace():
        end -= 1
    return start, end


def _formatting_spans(text, opening_markup, closing_markup):
    if opening_markup == closing_markup == "**":
        return [
            _DelimitedSpan(
                match.start(),
                match.end(),
                match.group(0)[:2],
                match.group(0)[-2:],
            )
            for match in _STRONG_PATTERN.finditer(text)
        ]

    if opening_markup == closing_markup == "*":
        return [
            _DelimitedSpan(
                match.start(),
                match.end(),
                match.group(0)[:1],
                match.group(0)[-1:],
            )
            for match in _EMPHASIS_PATTERN.finditer(text)
        ]

    if (
        opening_markup.casefold() == "<u>"
        and closing_markup.casefold() == "</u>"
    ):
        return [
            _DelimitedSpan(
                match.start(),
                match.end(),
                match.group(0)[:3],
                match.group(0)[-4:],
            )
            for match in _UNDERLINE_PATTERN.finditer(text)
        ]

    return []


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
    formatted_prefix, plain_prefix = _split_left_boundary(prefix)
    plain_suffix, formatted_suffix = _split_right_boundary(suffix)

    left = (
        span.opening + formatted_prefix + span.closing
        if formatted_prefix
        else ""
    )
    right = (
        span.opening + formatted_suffix + span.closing
        if formatted_suffix
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


def _merge_neighboring_formatted_spans(
    text,
    start,
    end,
    spans,
    opening_markup,
    closing_markup,
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

    merged_opening = (
        left.opening
        if (
            left.opening == right.opening
            and left.closing == right.closing
        )
        else opening_markup
    )
    merged_closing = (
        left.closing
        if (
            left.opening == right.opening
            and left.closing == right.closing
        )
        else closing_markup
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
        merged_opening + content + merged_closing
    )
    restored_start = (
        left.start
        + len(merged_opening)
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


def _toggle_adjacent_or_wrap(
    text,
    start,
    end,
    opening_markup,
    closing_markup,
):
    opening_length = len(opening_markup)
    closing_length = len(closing_markup)
    selected = text[start:end]
    before = start - opening_length
    after = end + closing_length

    if (
        before >= 0
        and text[before:start] == opening_markup
        and text[end:after] == closing_markup
    ):
        return InlineMarkupEdit(
            start=before,
            end=after,
            replacement=selected,
            selection_start=before,
            selection_end=before + len(selected),
        )

    if (
        selected.startswith(opening_markup)
        and selected.endswith(closing_markup)
        and len(selected) >= opening_length + closing_length
    ):
        content = selected[
            opening_length:len(selected) - closing_length
        ]
        return InlineMarkupEdit(
            start=start,
            end=end,
            replacement=content,
            selection_start=start,
            selection_end=start + len(content),
        )

    replacement = (
        opening_markup + selected + closing_markup
    )
    restored_start = start + opening_length
    return InlineMarkupEdit(
        start=start,
        end=end,
        replacement=replacement,
        selection_start=restored_start,
        selection_end=restored_start + len(selected),
    )
