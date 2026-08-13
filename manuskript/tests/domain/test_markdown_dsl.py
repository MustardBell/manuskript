import pytest

from manuskript.domain.markdown_dsl import (
    MarkdownDslExtensionResult,
    MarkdownDslNode,
    MarkdownDslParser,
    SourceSpan,
    render_wikilinks_as_markdown,
)


def test_wikilinks_use_obsidian_target_then_display_order_with_source_spans():
    source = "Олена entered [[Places/Kyiv|Києва]] quietly."

    tree = MarkdownDslParser().parse(source)
    link = tree.wikilinks[0]

    assert link.target == "Places/Kyiv"
    assert link.display == "Києва"
    assert link.rendered_text == "Києва"
    assert link.span.extract(source) == "[[Places/Kyiv|Києва]]"
    assert link.target_span.extract(source) == "Places/Kyiv"
    assert link.display_span.extract(source) == "Києва"


def test_wikilinks_in_code_or_escaped_source_remain_plain_markdown():
    source = (
        "\\[[escaped]] and `[[inline]]`\n"
        "```python\n[[fenced]]\n```\n"
        "[[actual]]"
    )

    tree = MarkdownDslParser().parse(source)

    assert tuple(link.target for link in tree.wikilinks) == ("actual",)


def test_malformed_wikilinks_report_diagnostics_without_consuming_prose():
    source = "Before [[]] and [[unclosed\nafter."

    tree = MarkdownDslParser().parse(source)

    assert not tree.wikilinks
    assert len(tree.diagnostics) == 2
    assert tree.source == source


def test_source_transformations_are_ordered_and_reject_overlap():
    tree = MarkdownDslParser().parse("[[One]] then [[Two|second]]")

    changed = tree.replace((
        (tree.wikilinks[0].target_span, "First"),
        (tree.wikilinks[1].target_span, "Second"),
    ))

    assert changed == "[[First]] then [[Second|second]]"
    with pytest.raises(ValueError, match="overlap"):
        tree.replace(((SourceSpan(0, 4), "a"), (SourceSpan(3, 6), "b")))


def test_reading_projection_shows_reference_text_without_making_a_link():
    source = "See [[Characters/Mara|her]] and [[Places/Vienna]]."

    rendered = render_wikilinks_as_markdown(source)

    assert rendered == "See her and Places/Vienna."
    assert MarkdownDslParser().parse(source).source == source


def test_embedded_reference_is_still_plain_display_text_in_projection():
    source = "![[Images/map.png|Map]]"

    link = MarkdownDslParser().parse(source).wikilinks[0]

    assert link.embedded
    assert link.span.extract(source) == source
    assert render_wikilinks_as_markdown(source) == "Map"


def test_reference_display_cannot_smuggle_a_markdown_hyperlink():
    source = "[[Target|<https://example.invalid>]]"

    assert render_wikilinks_as_markdown(source) == (
        r"\<https://example\.invalid\>"
    )


def test_incremental_edit_reparses_the_touched_line_and_shifts_later_spans():
    parser = MarkdownDslParser()
    source = "[[First]]\nordinary prose\n[[Third]]\n"
    tree = parser.parse(source)
    edit = SourceSpan(source.index("ordinary"), source.index(" prose"))

    updated = parser.update(tree, edit, "[[Second]]")

    assert updated.source == "[[First]]\n[[Second]] prose\n[[Third]]\n"
    assert tuple(link.target for link in updated.wikilinks) == (
        "First", "Second", "Third",
    )
    assert tuple(
        link.span.extract(updated.source) for link in updated.wikilinks
    ) == ("[[First]]", "[[Second]]", "[[Third]]")


def test_dsl_extensions_add_generic_nodes_without_owning_the_source():
    class CommentExtension:
        def parse(self, source, _excluded_spans):
            start = source.index("%%")
            return MarkdownDslExtensionResult(nodes=(
                MarkdownDslNode.from_mapping(
                    "comment", SourceSpan(start, len(source)),
                    {"visible": False},
                ),
            ))

    source = "Text %% private"
    tree = MarkdownDslParser((CommentExtension(),)).parse(source)

    assert tree.nodes[0].kind == "comment"
    assert dict(tree.nodes[0].attributes) == {"visible": False}
    assert tree.nodes[0].span.extract(source) == "%% private"
    assert tree.source == source


def test_dsl_extension_failure_becomes_a_diagnostic_and_keeps_prose():
    class BrokenExtension:
        def parse(self, _source, _excluded_spans):
            raise ValueError("invalid extension syntax")

    source = "Still editable."
    tree = MarkdownDslParser((BrokenExtension(),)).parse(source)

    assert tree.source == source
    assert tree.diagnostics[0].severity == "error"
    assert "BrokenExtension" in tree.diagnostics[0].message
