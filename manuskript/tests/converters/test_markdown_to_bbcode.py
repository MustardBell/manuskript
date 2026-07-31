from manuskript.converters.markdownToBBCode import markdown_to_bbcode


def test_markdown_to_bbcode_converts_native_markup():
    converted = markdown_to_bbcode(
        "# Heading\n\n**Bold** and *italic* with "
        "[link](https://example.com)"
    )

    assert "[h1]Heading[/h1]" in converted
    assert "[b]Bold[/b]" in converted
    assert "[i]italic[/i]" in converted
    assert "[url=https://example.com]link[/url]" in converted
