#!/usr/bin/env python
# --!-- coding: utf8 --!--

# Version 0 of file saving format.
# Was used at the beginning and up until version XXX when
# it was superseded by Version 1, which is more open and flexible
from PyQt5.QtCore import QModelIndex, Qt
from PyQt5.QtGui import QColor, QStandardItem
from PyQt5.QtWidgets import qApp
from lxml import etree as ET

from manuskript.domain.persistence import (
    ProjectLoadResult,
    ProjectSaveResult,
)
from manuskript.functions import iconColor, iconFromColorString
from manuskript.load_save.legacy_archive import (
    LegacyArchiveReadError,
    LegacyArchiveWriteError,
    Version0ProjectArchive,
)
from manuskript.models.characterModel import Character, CharacterInfo

import logging
LOGGER = logging.getLogger(__name__)

compression = Version0ProjectArchive.COMPRESSION

###########################################################################################
# SAVE
###########################################################################################

def saveProject(context, archive=None):
    """
    Saves the whole project. Call this function to save the project in Version 0 format.
    """

    files = []
    files.append((saveStandardItemModelXML(context.models.flat_data),
                  "flatModel.xml"))
    LOGGER.error("File format 0 does not save characters!")
    # files.append((saveStandardItemModelXML(context.models.characters),
    #               "perso.xml"))
    files.append((saveStandardItemModelXML(context.models.world),
                  "world.xml"))
    files.append((saveStandardItemModelXML(context.models.labels),
                  "labels.xml"))
    files.append((saveStandardItemModelXML(context.models.statuses),
                  "status.xml"))
    files.append((saveStandardItemModelXML(context.models.plots),
                  "plots.xml"))
    files.append((context.models.outline.saveToXML(),
                  "outline.xml"))
    files.append((context.settings.save(),
                  "settings.pickle"))

    archive = (
        archive if archive is not None else Version0ProjectArchive()
    )
    try:
        archive.write(context.project_file, files)
    except LegacyArchiveWriteError as error:
        LOGGER.error("%s", error)
        return ProjectSaveResult(
            failed_files=(context.project_file,)
        )
    return ProjectSaveResult()

def saveFilesToZip(files, zipname):
    """Saves given files to zipname.
    files is actually a list of (content, filename)."""

    Version0ProjectArchive().write(zipname, files)

def saveStandardItemModelXML(mdl, xml=None):
    """Saves the given QStandardItemModel to XML.
    If xml (filename) is given, saves to xml. Otherwise returns as string."""

    root = ET.Element("model")
    root.attrib["version"] = qApp.applicationVersion()

    # Header
    header = ET.SubElement(root, "header")
    vHeader = ET.SubElement(header, "vertical")
    for x in range(mdl.rowCount()):
        vH = ET.SubElement(vHeader, "label")
        vH.attrib["row"] = str(x)
        vH.attrib["text"] = str(mdl.headerData(x, Qt.Vertical))

    hHeader = ET.SubElement(header, "horizontal")
    for y in range(mdl.columnCount()):
        hH = ET.SubElement(hHeader, "label")
        hH.attrib["row"] = str(y)
        hH.attrib["text"] = str(mdl.headerData(y, Qt.Horizontal))

    # Data
    data = ET.SubElement(root, "data")
    saveItem(data, mdl)

    # LOGGER.info("Saving to {}.".format(xml))
    if xml:
        ET.ElementTree(root).write(xml, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    else:
        return ET.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)


def saveItem(root, mdl, parent=QModelIndex()):
    for x in range(mdl.rowCount(parent)):
        row = ET.SubElement(root, "row")
        row.attrib["row"] = str(x)

        for y in range(mdl.columnCount(parent)):
            col = ET.SubElement(row, "col")
            col.attrib["col"] = str(y)
            if mdl.data(mdl.index(x, y, parent), Qt.DecorationRole) != None:
                color = iconColor(mdl.data(mdl.index(x, y, parent), Qt.DecorationRole)).name(QColor.HexArgb)
                col.attrib["color"] = color if color != "#ff000000" else "#00000000"
            if mdl.data(mdl.index(x, y, parent)) != "":
                col.text = mdl.data(mdl.index(x, y, parent))
            if mdl.hasChildren(mdl.index(x, y, parent)):
                saveItem(col, mdl, mdl.index(x, y, parent))

###########################################################################################
# LOAD
###########################################################################################

def loadProject(context, archive=None):
    project = context.project_file

    archive = (
        archive if archive is not None else Version0ProjectArchive()
    )
    try:
        files = archive.read(project)
    except LegacyArchiveReadError as error:
        LOGGER.error("%s", error)
        return ProjectLoadResult(fatal_errors=(str(error),))

    errors = []

    if "flatModel.xml" in files:
        loadStandardItemModelXML(context.models.flat_data,
                                 files["flatModel.xml"], fromString=True)
    else:
        errors.append("flatModel.xml")

    if "perso.xml" in files:
        loadStandardItemModelXMLForCharacters(context.models.characters, files["perso.xml"])
    else:
        errors.append("perso.xml")

    if "world.xml" in files:
        loadStandardItemModelXML(context.models.world,
                                 files["world.xml"], fromString=True)
    else:
        errors.append("world.xml")

    if "labels.xml" in files:
        loadStandardItemModelXML(context.models.labels,
                                 files["labels.xml"], fromString=True)
    else:
        errors.append("labels.xml")

    if "status.xml" in files:
        loadStandardItemModelXML(context.models.statuses,
                                 files["status.xml"], fromString=True)
    else:
        errors.append("status.xml")

    if "plots.xml" in files:
        loadStandardItemModelXML(context.models.plots,
                                 files["plots.xml"], fromString=True)
    else:
        errors.append("plots.xml")

    if "outline.xml" in files:
        context.models.outline.loadFromXML(files["outline.xml"], fromString=True)
    else:
        errors.append("outline.xml")

    if "settings.txt" in files:
        context.settings.load(files["settings.txt"], fromString=True, protocol=0)
    else:
        errors.append("settings.txt")

    if "settings.pickle" in files:
        LOGGER.info("Pickle settings files are no longer supported for security reasons. You can delete it from your data.")

    return ProjectLoadResult(missing_files=tuple(errors))


def loadFilesFromZip(zipname):
    """Returns the content of zipfile as a dict of filename:content."""
    return Version0ProjectArchive().read(zipname)


def loadStandardItemModelXML(mdl, xml, fromString=False):
    """Load data to a QStandardItemModel mdl from xml.
    By default xml is a filename. If fromString=True, xml is a string containing the data."""

    # LOGGER.info("Loading {}...".format(xml))

    try:
        root = (
            ET.fromstring(xml)
            if fromString
            else ET.parse(xml).getroot()
        )
    except (OSError, ValueError, TypeError, ET.XMLSyntaxError) as error:
        LOGGER.error(
            "Failed to load XML for QStandardItemModel (%s): %s",
            xml,
            error,
        )
        return False

    # Header
    hLabels = []
    vLabels = []
    for l in root.find("header").find("horizontal").findall("label"):
        hLabels.append(l.attrib["text"])
    for l in root.find("header").find("vertical").findall("label"):
        vLabels.append(l.attrib["text"])

    # LOGGER.debug(root.find("header").find("vertical").text)

    # mdl.setVerticalHeaderLabels(vLabels)
    # mdl.setHorizontalHeaderLabels(hLabels)

    # Populates with empty items
    for i in enumerate(vLabels):
        row = []
        for r in enumerate(hLabels):
            row.append(QStandardItem())
        mdl.appendRow(row)

    # Data
    data = root.find("data")
    loadItem(data, mdl)

    return True


def loadItem(root, mdl, parent=QModelIndex()):
    for row in root:
        r = int(row.attrib["row"])
        for col in row:
            c = int(col.attrib["col"])
            item = mdl.itemFromIndex(mdl.index(r, c, parent))
            if not item:
                item = QStandardItem()
                mdl.itemFromIndex(parent).setChild(r, c, item)

            if col.text:
                # mdl.setData(mdl.index(r, c, parent), col.text)
                item.setText(col.text)

            if "color" in col.attrib:
                # mdl.itemFromIndex(mdl.index(r, c, parent)).setIcon(iconFromColorString(col.attrib["color"]))
                item.setIcon(iconFromColorString(col.attrib["color"]))

            if len(col) != 0:
                # loadItem(col, mdl, mdl.index(r, c, parent))
                loadItem(col, mdl, mdl.indexFromItem(item))


def loadStandardItemModelXMLForCharacters(mdl, xml):
    """
    Loads a standardItemModel saved to XML by version 0, but for the new characterModel.
    @param mdl: characterModel
    @param xml: the content of the xml
    @return: nothing
    """
    root = ET.fromstring(xml)
    data = root.find("data")

    for row in data:
        char = Character(mdl)

        for col in row:
            c = int(col.attrib["col"])

            # Value
            if col.text:
                char._data[c] = col.text

            # Color
            if "color" in col.attrib:
                char.setColor(QColor(col.attrib["color"]))

            # Infos
            if len(col) != 0:
                for rrow in col:
                    info = CharacterInfo(char)
                    for ccol in rrow:
                        cc = int(ccol.attrib["col"])
                        if cc == 11 and ccol.text:
                            info.description = ccol.text
                        if cc == 12 and ccol.text:
                            info.value = ccol.text
                    char.infos.append(info)

        mdl.characters.append(char)
