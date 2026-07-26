from lxml import etree as ET


def parse_project_xml(value):
    """Parse trusted project XML without lxml's small text-node limit.

    Manuskript revisions can legitimately contain text nodes larger than
    lxml's default 10 MB limit. Project files are local, trusted input, so
    enabling ``huge_tree`` here keeps that compatibility decision explicit
    and contained within the persistence layer.
    """
    parser = ET.XMLParser(huge_tree=True)
    return ET.fromstring(value, parser=parser)
