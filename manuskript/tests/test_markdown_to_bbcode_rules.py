"""BBCode conversion as rules, extendable without affecting core output."""

import re

from manuskript.converters.markdownToBBCode import (
    BBCODE_RULES,
    BBCodeConverter,
    MarkupRule,
    markdown_to_bbcode,
)


def test_the_function_and_the_converter_agree():
    source = (
        "# Heading\n\n**bold** and *italic* and `code`\n\n"
        "> quoted\n\n    indented\n\n[link](http://example.com)\n"
        "-> arrow, a -- dash, a - b\n"
    )

    assert markdown_to_bbcode(source) == BBCodeConverter().convert(source)


def test_non_text_is_returned_untouched():
    for value in (None, 0, "", [], {}):
        assert markdown_to_bbcode(value) == value


def test_rule_order_is_preserved_where_it_matters():
    """`** -> **` must win over the bare `->` literal."""
    assert markdown_to_bbcode("** -> **") == "[size=6]→[/size]"
    assert markdown_to_bbcode("a -> b") == "a → b"
    # Deepest heading first, so ###### is not consumed by the # rule.
    assert markdown_to_bbcode("###### six") == "[h6]six[/h6]"


def test_extended_adds_rules_without_touching_the_default():
    default = BBCodeConverter()
    mention = MarkupRule(r"@(\w+)", r"[i]\1[/i]", re.IGNORECASE)

    extended = default.extended(mention)

    assert extended.convert("@someone") == "[i]someone[/i]"
    # The converter core hands to everyone else is unchanged.
    assert default.convert("@someone") == "@someone"
    assert markdown_to_bbcode("@someone") == "@someone"
    assert len(extended.rules) == len(default.rules) + 1


def test_extended_keeps_the_original_rules_in_front():
    extended = BBCodeConverter().extended(
        MarkupRule("[b]", "<strong>", literal=True)
    )

    # Core turns ** into [b] first, then the plugin rule rewrites it.
    assert extended.convert("**x**") == "<strong>x[/b]"


def test_a_literal_rule_does_not_interpret_regex():
    converter = BBCodeConverter(
        rules=[MarkupRule("a.c", "HIT", literal=True)]
    )

    assert converter.convert("a.c") == "HIT"
    assert converter.convert("abc") == "abc"


def test_the_published_rule_list_is_data():
    assert BBCODE_RULES
    assert all(isinstance(rule, MarkupRule) for rule in BBCODE_RULES)
    # Frozen, so a plugin cannot mutate the shared default in place.
    assert BBCodeConverter().rules is not None
    for rule in BBCODE_RULES:
        try:
            rule.pattern = "mutated"
        except Exception:
            continue
        raise AssertionError("rules must be immutable")
