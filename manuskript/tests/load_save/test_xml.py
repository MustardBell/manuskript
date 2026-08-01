from manuskript.load_save.xml import parse_project_xml


def test_project_xml_parser_accepts_large_revision_text_nodes():
    revision = "x" * (10 * 1024 * 1024 + 1)

    root = parse_project_xml(
        "<revisions><revision>{}</revision></revisions>".format(
            revision
        ).encode("utf-8")
    )

    assert root[0].text == revision
