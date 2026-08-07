#!/usr/bin/env python
# --!-- coding: utf8 --!--

# Version 1 of file saving format.
# Aims at providing a plain-text way of saving a project
# (except for some elements), allowing collaborative work
# versioning and third-party editing.

import os
import re
import string
from collections import OrderedDict

from PyQt5.QtCore import Qt, QModelIndex
from PyQt5.QtGui import QColor, QStandardItem

from manuskript.domain.persistence import (
    ProjectLoadResult,
    ProjectSaveResult,
)
from manuskript.domain.revisions import RevisionConfiguration
from manuskript.enums import Character, World, Plot, PlotStep, Outline
from manuskript.functions import iconColor, iconFromColorString
from manuskript.converters import HTML2PlainText
from lxml import etree as ET

from manuskript.load_save.project_files import Version1ProjectFiles
from manuskript.load_save.xml import parse_project_xml
from manuskript.models.characterModel import CharacterInfo
from manuskript.models import outlineItem

import logging
LOGGER = logging.getLogger(__name__)

characterMap = OrderedDict([
    (Character.name, "Name"),
    (Character.ID,   "ID"),
    (Character.importance, "Importance"),
    (Character.pov, "POV"),
    (Character.motivation, "Motivation"),
    (Character.goal, "Goal"),
    (Character.conflict, "Conflict"),
    (Character.epiphany, "Epiphany"),
    (Character.summarySentence, "Phrase Summary"),
    (Character.summaryPara, "Paragraph Summary"),
    (Character.summaryFull, "Full Summary"),
    (Character.notes, "Notes")
])


def formatMetaData(name, value, tabLength=10):

    # Multiline formatting
    if len(value.split("\n")) > 1:
        value = "\n".join([" " * (tabLength + 1) + l for l in value.split("\n")])[tabLength + 1:]

    # Avoid empty description (don't know how much MMD loves that)
    if name == "":
        name = "None"

    # Escapes ":" in name
    name = name.replace(":", "_.._")

    return "{name}:{spaces}{value}\n".format(
        name=name,
        spaces=" " * (tabLength - len(name)),
        value=value
    )


def slugify(name):
    """
    A basic slug function, that escapes all spaces to "_" and all non letters/digits to "-".
    @param name: name to slugify (str)
    @return: str
    """
    valid = string.ascii_letters + string.digits
    newName = ""
    for c in name:
        if c in valid:
            newName += c
        elif c in string.whitespace:
            newName += "_"
        else:
            newName += "-"
    return newName


def saveProject(
    context,
    zip=None,
    cache=None,
    file_access=None,
):
    """
    Saves the project. If zip is False, the project is saved as a multitude of plain-text files for the most parts
    and some XML or zip? for settings and stuff.
    If zip is True, everything is saved as a single zipped file. Easier to carry around, but does not allow
    collaborative work, versioning, or third-party editing.
    @param zip: if True, saves as a single file. If False, saves as plain-text. If None, tries to determine based on
    settings.
    @return: True if successful, False otherwise.
    """
    if cache is None:
        cache = {}
    if file_access is None:
        file_access = Version1ProjectFiles()

    if zip == None:
        zip = context.settings.saveToZip

    LOGGER.info("Saving to: %s", "zip" if zip else "folder")

    # List of files to be written
    files = []
    # List of files to be moved
    moves = []

    project = context.project_file

    # Sanity check (see PR-583): make sure we actually have a current project.
    if project == None:
        LOGGER.error("Cannot save project because there is no current project in the UI.")
        return ProjectSaveResult(failed_files=(project,))

    # File format version
    files.append(("MANUSKRIPT", "1"))

    # General infos (book and author)
    # Saved in plain text, in infos.txt

    path = "infos.txt"
    content = ""
    for name, col in [
            ("Title", 0),
            ("Subtitle", 1),
            ("Serie", 2),
            ("Volume", 3),
            ("Genre", 4),
            ("License", 5),
            ("Author", 6),
            ("Email", 7),
            ]:
        item = context.models.flat_data.item(0, col)
        if item:
            val = item.text().strip()
        else:
            val = ""

        if val:
            content += "{name}:{spaces}{value}\n".format(
                name=name,
                spaces=" " * (15 - len(name)),
                value=val
            )
    files.append((path, content))

    ####################################################################################################################
    # Summary
    # In plain text, in summary.txt

    path = "summary.txt"
    content = ""
    for name, col in [
            ("Situation", 0),
            ("Sentence", 1),
            ("Paragraph", 2),
            ("Page", 3),
            ("Full", 4),
            ]:
        item = context.models.flat_data.item(1, col)
        if item:
            val = item.text().strip()
        else:
            val = ""

        if val:
            content += formatMetaData(name, val, 12)

    files.append((path, content))

    ####################################################################################################################
    # Label & Status
    # In plain text

    for mdl, path in [
        (context.models.statuses, "status.txt"),
        (context.models.labels, "labels.txt")
    ]:

        content = ""

        # We skip the first row, which is empty and transparent
        for i in range(1, mdl.rowCount()):
            color = ""
            if mdl.data(mdl.index(i, 0), Qt.DecorationRole) != None:
                color = iconColor(mdl.data(mdl.index(i, 0), Qt.DecorationRole)).name(QColor.HexRgb)
                color = color if color != "#ff000000" else "#00000000"

            text = mdl.data(mdl.index(i, 0))

            if text:
                content += "{name}{color}\n".format(
                    name=text,
                    color="" if color == "" else ":" + " " * (20 - len(text)) + color
                )

        files.append((path, content))

    ####################################################################################################################
    # Characters
    # In a character folder

    path = os.path.join("characters", "{name}.txt")
    mdl = context.models.characters

    # Review characters
    for c in mdl.characters:

        # Generates file's content
        content = ""
        for m in characterMap:
            val = mdl.data(c.index(m.value)).strip()
            if val:
                content += formatMetaData(characterMap[m], val, 20)

        # Character's color:
        content += formatMetaData("Color", c.color().name(QColor.HexRgb), 20)

        # Character's infos
        for info in c.infos:
            content += formatMetaData(info.description, info.value, 20)

        # generate file's path
        cpath = path.format(name="{ID}-{slugName}".format(
            ID=c.ID(),
            slugName=slugify(c.name())
        ))

        # Has the character been renamed?
        if c.lastPath and cpath != c.lastPath:
            moves.append((c.lastPath, cpath))

        # Update character's path
        c.lastPath = cpath

        files.append((cpath, content))

    ####################################################################################################################
    # Texts
    # In an outline folder

    mdl = context.models.outline

    # Go through the tree
    f, m, _removes = exportOutlineItem(mdl.rootItem)
    files += f
    moves += m

    # Writes revisions (if asked for)
    revision_configuration = RevisionConfiguration.from_mapping(
        context.settings.revisions
    )
    if revision_configuration.uses_internal_snapshots:
        files.append(("revisions.xml", mdl.saveToXML()))

    ####################################################################################################################
    # World
    # Either in an XML file, or in lots of plain texts?
    # More probably text, since there might be writing done in third-party.

    path = "world.opml"
    mdl = context.models.world

    root = ET.Element("opml")
    root.attrib["version"] = "1.0"
    body = ET.SubElement(root, "body")
    addWorldItem(body, mdl)
    content = ET.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    files.append((path, content))

    ####################################################################################################################
    # Plots (context.models.plots)
    # Either in XML or lots of plain texts?
    # More probably XML since there is not really a lot if writing to do (third-party)

    path = "plots.xml"
    mdl = context.models.plots

    root = ET.Element("root")
    addPlotItem(root, mdl)
    content = ET.tostring(root, encoding="UTF-8", xml_declaration=True, pretty_print=True)
    files.append((path, content))

    ####################################################################################################################
    # Settings
    # Saved in readable text (json) for easier versioning. But they mustn't be shared, it seems.
    # Maybe include them only if zipped?
    # Well, for now, we keep them here...

    files.append(("settings.txt", context.settings.save(protocol=0)))
    files += list(context.models.plugin_data.project_files())

    return file_access.write(
        project,
        zipped=bool(zip),
        files=files,
        moves=moves,
        cache=cache,
    )


def addWorldItem(root, mdl, parent=QModelIndex()):
    """
    Lists elements in a world model and create an OPML xml file.
    @param root: an Etree element
    @param mdl:  a worldModel
    @param parent: the parent index in the world model
    @return: root, to which sub element have been added
    """
    # List every row (every world item)
    for x in range(mdl.rowCount(parent)):

        # For each row, create an outline item.
        outline = ET.SubElement(root, "outline")
        for y in range(mdl.columnCount(parent)):

            val = mdl.data(mdl.index(x, y, parent))

            if not val:
                continue

            for w in World:
                if y == w.value:
                    outline.attrib[w.name] = val

            if mdl.hasChildren(mdl.index(x, y, parent)):
                addWorldItem(outline, mdl, mdl.index(x, y, parent))

    return root


def addPlotItem(root, mdl, parent=QModelIndex()):
    """
    Lists elements in a plot model and create an xml file.
    @param root: an Etree element
    @param mdl:  a plotModel
    @param parent: the parent index in the plot model
    @return: root, to which sub element have been added
    """

    # List every row (every plot item)
    for x in range(mdl.rowCount(parent)):

        # For each row, create an outline item.
        outline = ET.SubElement(root, "plot")
        for y in range(mdl.columnCount(parent)):

            index = mdl.index(x, y, parent)
            val = mdl.data(index)
            #
            # if not val:
            #     continue

            for w in Plot:
                if y == w.value and val:
                    outline.attrib[w.name] = val

            # List characters as attrib
            if y == Plot.characters:
                if mdl.hasChildren(index):
                    characters = []
                    for cX in range(mdl.rowCount(index)):
                        for cY in range(mdl.columnCount(index)):
                            cIndex = mdl.index(cX, cY, index)
                            characters.append(mdl.data(cIndex))
                    outline.attrib[Plot.characters.name] = ",".join(characters)

                elif Plot.characters.name in outline.attrib:
                    outline.attrib.pop(Plot.characters.name)

            # List resolution steps as sub items
            elif y == Plot.steps:
                if mdl.hasChildren(index):
                    for cX in range(mdl.rowCount(index)):
                        step = ET.SubElement(outline, "step")
                        for cY in range(mdl.columnCount(index)):
                            cIndex = mdl.index(cX, cY, index)
                            # If empty, returns None, which creates trouble later with lxml, so default to ""
                            val = mdl.data(cIndex) or ""

                            for w in PlotStep:
                                if cY == w.value and w.name:
                                    step.attrib[w.name] = val

                elif Plot.steps.name in outline.attrib:
                    outline.attrib.pop(Plot.steps.name)

    return root


def exportOutlineItem(root):
    """
    Takes an outline item, and returns three lists:
    1. of (`filename`, `content`), representing the whole tree of files to be written, in multimarkdown.
    2. of (`filename`, `filename`) listing files to be moved
    3. of `filename`, representing files to be removed.

    @param root: OutlineItem
    @return: [(str, str)], [(str, str)], [str]
    """

    files = []
    moves = []
    removes = []

    k = 0
    for child in root.children():
        spath = os.path.join(*outlineItemPath(child))

        k += 1

        # Has the item been renamed?
        lp = child._lastPath
        if lp and spath != lp:
            moves.append((lp, spath))
            LOGGER.debug("%s has been renamed (%s → %s)", child.title(), lp,  spath)
            LOGGER.debug(" → We mark for moving: %s", lp)

        # Updates item last's path
        child._lastPath = spath

        # Generating content
        if child.type() == "folder":
            fpath = os.path.join(spath, "folder.txt")
            content = outlineToMMD(child)
            files.append((fpath, content))

        elif child.type() == "md":
            content = outlineToMMD(child)
            files.append((spath, content))

        else:
            LOGGER.debug("Unknown type: %s", child.type())

        f, m, r = exportOutlineItem(child)
        files += f
        moves += m
        removes += r

    return files, moves, removes


def outlineItemPath(item):
    """
    Returns the outlineItem file path (like the path where it will be written on the disk). As a list of folder's
    name. To be joined by os.path.join.
    @param item: outlineItem
    @return: list of folder's names
    """
    # Root item
    if not item.parent():
        return ["outline"]
    else:
        # Count the number of siblings for padding '0'
        siblings = item.parent().childCount()

        # We check if multiple items have the same name
        # If so, we add "-ID" to their name
        siblingsNames = [s.title() for s in item.parent().children()]
        if siblingsNames.count(item.title()) > 1:
            title = "{}-{}".format(item.title(), item.ID())
        else:
            title = item.title()

        name = "{ID}-{name}{ext}".format(
            ID=str(item.row()).zfill(len(str(siblings))),
            name=slugify(title),
            ext="" if item.type() == "folder" else ".md"
        )
        return outlineItemPath(item.parent()) + [name]


def outlineToMMD(item):
    content = ""

    # We don't want to write some datas (computed)
    #
    # charCount joined the list late. It was written to every document
    # file and read back into every item on load -- and then thrown away
    # microseconds later, because loading sets the metadata first and the
    # text last, and setting text recomputes both counts. So the stored
    # number was never once consulted: pure write-only noise, one changed
    # header line in every diff of every document anybody typed in, and a
    # number that depended on the countSpaces preference, so two people
    # with the same text wrote different bytes.
    #
    # Its absent twin, wordCount, has been in this list since the list was
    # written in 2016. Nothing chose the difference.
    exclude = [
        Outline.wordCount,
        Outline.charCount,
        Outline.goal,
        Outline.goalPercentage,
        Outline.revisions,
        Outline.text,
    ]
    # We want to force some data even if they're empty
    force = [Outline.compile]

    for attrib in Outline:
        if attrib in exclude:
            continue
        val = item.data(attrib.value)
        if val or attrib in force:
            content += formatMetaData(attrib.name, str(val), 15)

    content += "\n\n"
    content += item.data(Outline.text)

    return content

########################################################################################################################
# LOAD
########################################################################################################################

def loadProject(
    context,
    zip=None,
    cache=None,
    file_access=None,
):
    """
    Loads a project.
    @param context: the project path, models, and settings to hydrate.
    @param zip: whether the project is a zipped or not.
    @return: an array of errors, empty if None.
    """
    project = context.project_file
    if cache is None:
        cache = {}
    if file_access is None:
        file_access = Version1ProjectFiles()

    errors = list()

    ####################################################################################################################
    # Read and store everything in a dict

    LOGGER.debug("Loading {} ({})".format(project, "zip" if zip else "folder"))
    read_result = file_access.read(project, zipped=bool(zip))
    files = read_result.files
    context.models.plugin_data.load_project_files(files)
    if not zip:
        cache.clear()
        cache.update(files)

    # Sort files by keys
    files = OrderedDict(sorted(files.items()))

    ####################################################################################################################
    # Settings

    if "settings.txt" in files:
        context.settings.load(files["settings.txt"], fromString=True, protocol=0)
    else:
        errors.append("settings.txt")

    # Just to be sure
    context.settings.saveToZip = True if zip else False
    context.settings.defaultTextType = "md"

    ####################################################################################################################
    # Labels

    mdl = context.models.labels
    mdl.appendRow(QStandardItem(""))  # Empty = No labels
    if "labels.txt" in files:
        LOGGER.debug("Reading labels:")
        for s in files["labels.txt"].split("\n"):
            if not s:
                continue

            m = re.search(r"^(.*?):\s*(.*)$", s)
            txt = m.group(1)
            col = m.group(2)
            LOGGER.debug("* Add status: {} ({})".format(txt, col))
            icon = iconFromColorString(col)
            mdl.appendRow(QStandardItem(icon, txt))

    else:
        errors.append("labels.txt")

    ####################################################################################################################
    # Status

    mdl = context.models.statuses
    mdl.appendRow(QStandardItem(""))  # Empty = No status
    if "status.txt" in files:
        LOGGER.debug("Reading status:")
        for s in files["status.txt"].split("\n"):
            if not s:
                continue
            LOGGER.debug("* Add status: %s", s)
            mdl.appendRow(QStandardItem(s))
    else:
        errors.append("status.txt")

    ####################################################################################################################
    # Infos

    mdl = context.models.flat_data
    if "infos.txt" in files:
        md, body = parseMMDFile(files["infos.txt"], asDict=True)

        row = []
        for name in ["Title", "Subtitle", "Serie", "Volume", "Genre", "License", "Author", "Email"]:
            row.append(QStandardItem(md.get(name, "")))

        mdl.appendRow(row)

    else:
        errors.append("infos.txt")

    ####################################################################################################################
    # Summary

    mdl = context.models.flat_data
    if "summary.txt" in files:
        md, body = parseMMDFile(files["summary.txt"], asDict=True)

        row = []
        for name in ["Situation", "Sentence", "Paragraph", "Page", "Full"]:
            row.append(QStandardItem(md.get(name, "")))

        mdl.appendRow(row)

    else:
        errors.append("summary.txt")

    ####################################################################################################################
    # Plots

    mdl = context.models.plots
    if "plots.xml" in files:
        LOGGER.debug("Reading plots:")
        # xml = bytearray(files["plots.xml"], "utf-8")
        root = ET.fromstring(files["plots.xml"])

        for plot in root:
            # Create row
            row = getStandardItemRowFromXMLEnum(plot, Plot)

            # Log
            LOGGER.debug("* Add plot: %s", row[0].text())

            # Characters
            if row[Plot.characters].text():
                IDs = row[Plot.characters].text().split(",")
                item = QStandardItem()
                for ID in IDs:
                    item.appendRow(QStandardItem(ID.strip()))
                row[Plot.characters] = item

            # Subplots
            for step in plot:
                row[Plot.steps].appendRow(
                    getStandardItemRowFromXMLEnum(step, PlotStep)
                )

            # Add row to the model
            mdl.appendRow(row)

    else:
        errors.append("plots.xml")

    ####################################################################################################################
    # World

    mdl = context.models.world
    if "world.opml" in files:
        LOGGER.debug("Reading World:")
        # xml = bytearray(files["plots.xml"], "utf-8")
        root = ET.fromstring(files["world.opml"])
        body = root.find("body")

        for outline in body:
            row = getOutlineItem(outline, World)
            mdl.appendRow(row)

    else:
        errors.append("world.opml")

    ####################################################################################################################
    # Characters

    mdl = context.models.characters
    LOGGER.debug("Reading Characters:")
    for f in [f for f in files if "characters" in f]:
        md, body = parseMMDFile(files[f])
        c = mdl.addCharacter()
        c.lastPath = f

        color = False
        for desc, val in md:

            # Base infos
            if desc in characterMap.values():
                key = [key for key, value in characterMap.items() if value == desc][0]
                index = c.index(key.value)
                mdl.setData(index, val)

            # Character color
            elif desc == "Color" and not color:
                c.setColor(QColor(val))
                # We remember the first time we found "Color": it is the icon color.
                # If "Color" comes a second time, it is a Character's info.
                color = True

            # Character's infos
            else:
                c.infos.append(CharacterInfo(c, desc, val))

        LOGGER.debug("* Adds {} ({})".format(c.name(), c.ID()))

    ####################################################################################################################
    # Texts
    # We read outline form the outline folder. If revisions are saved, then there's also a revisions.xml which contains
    # everything, but the outline folder takes precedence (in cases it's been edited outside of manuskript.

    mdl = context.models.outline
    LOGGER.debug("Reading outline:")
    paths = [f for f in files if "outline" in f]
    outline = OrderedDict()

    # We create a structure of imbricated OrderedDict to store the whole tree.
    for f in paths:
        split = f.split(os.path.sep)[1:]
        # LOGGER.debug("* %s", split)

        last = ""
        parent = outline
        parentLastPath = "outline"
        for i in split:
            if last:
                parent = parent[last]
                parentLastPath = os.path.join(parentLastPath, last)
            last = i

            if not i in parent:
                # If not last item, then it is a folder
                if i != split[-1]:
                    parent[i] = OrderedDict()

                # If file, we store it
                else:
                    parent[i] = files[f]

                # We store f to add it later as lastPath
                parent[i + ":lastPath"] = os.path.join(parentLastPath, i)



    # We now just have to recursively add items.
    addTextItems(mdl, outline)

    # Adds revisions
    if "revisions.xml" in files:
        root = parse_project_xml(files["revisions.xml"])
        appendRevisions(mdl, root)

    # Check IDS
    mdl.rootItem.checkIDs()

    return ProjectLoadResult(
        missing_files=tuple(errors),
        unreadable_files=read_result.unreadable_files,
    )


def addTextItems(mdl, odict, parent=None):
    """
    Adds a text / outline items from an OrderedDict.
    @param mdl: model to add to
    @param odict: OrderedDict
    @return: nothing
    """
    if parent is None:
        parent = mdl.rootItem

    for k in odict:

        # In case k is a folder:
        if (type(odict[k]) == OrderedDict) and ("folder.txt" in odict[k]):

            # Adds folder
            LOGGER.debug("{}* Adds {} to {} (folder)".format("  " * parent.level(), k, parent.title()))
            item = outlineFromMMD(odict[k]["folder.txt"], parent=parent)
            item._lastPath = odict[k + ":lastPath"]

            # Read content
            addTextItems(mdl, odict[k], parent=item)

        if (":lastPath" in k) or (k == "folder.txt"):
            continue

        # k is not a folder
        if type(odict[k]) == str:
            try:
                LOGGER.debug("{}* Adds {} to {} (file)".format("  " * parent.level(), k, parent.title()))
                item = outlineFromMMD(odict[k], parent=parent)
                item._lastPath = odict[k + ":lastPath"]
            except KeyError:
                LOGGER.error(f"Failed to add file {k}")
        else:
            LOGGER.debug(f"Strange things in file {k}")


def outlineFromMMD(text, parent):
    """
    Creates outlineItem from multimarkdown file.
    @param text: content of the file
    @param parent: appends item to parent (outlineItem)
    @return: outlineItem
    """

    md, body = parseMMDFile(text, asDict=True)

    # Assign ID on creation, to avoid generating a new ID for this object
    item = outlineItem(parent=parent, ID=md.pop('ID'))

    # Store metadata
    for k in md:
        if k in Outline.__members__:
            item.setData(Outline.__members__[k], str(md[k]))

    # Store body
    item.setData(Outline.text, str(body))

    # Set file format to "md"
    # (Old version of manuskript had different file formats: text, t2t, html and md)
    # If file format is html, convert to plain text:
    if item.type() == "html":
        item.setData(Outline.text, HTML2PlainText(body))
    if item.type() in ["txt", "t2t", "html"]:
        item.setData(Outline.type, "md")

    return item


def appendRevisions(mdl, root):
    """
    Parse etree item to find outlineItem's with revisions, and adds them to model `mdl`.
    @param mdl: outlineModel
    @param root: etree
    @return: nothing
    """
    for child in root:
        # Recursively go through items
        if child.tag == "outlineItem":
            appendRevisions(mdl, child)

        # Revision found.
        elif child.tag == "revision":
            # Get root's ID
            ID = root.attrib["ID"]
            if not ID:
                LOGGER.debug("* Serious problem: no ID!")
                LOGGER.error("Revision has no ID associated!")
                continue

            # Find outline item in model
            item = mdl.getItemByID(ID)
            if not item:
                LOGGER.debug("* Error: no item whose ID is %s", ID)
                LOGGER.error("Could not identify the item matching the revision ID.")
                continue

            # Store revision
            LOGGER.debug("* Appends revision ({}) to {}".format(child.attrib["timestamp"], item.title()))
            item.appendRevision(child.attrib["timestamp"], child.attrib["text"])


def getOutlineItem(item, enum):
    """
    Reads outline items from an opml file. Returns a row of QStandardItem, easy to add to a QStandardItemModel.
    @param item: etree item
    @param enum: enum to read keys from
    @return: [QStandardItem]
    """
    row = getStandardItemRowFromXMLEnum(item, enum)
    LOGGER.debug("* Add worldItem: %s", row[0].text())
    for child in item:
        sub = getOutlineItem(child, enum)
        row[0].appendRow(sub)

    return row


def getStandardItemRowFromXMLEnum(item, enum):
    """
    Reads and etree item and creates a row of QStandardItems by cross-referencing an enum.
    Returns a list of QStandardItems that can be added to a QStandardItemModel by appendRow.
    @param item: the etree item
    @param enum: the enum
    @return: list of QStandardItems
    """
    row = []
    for i in range(len(enum)):
        row.append(QStandardItem(""))

    for name in item.attrib:
        if name in enum.__members__:
            row[enum[name].value] = QStandardItem(item.attrib[name])
    return row

def parseMMDFile(text, asDict=False):
    """
    Takes the content of a MultiMarkDown file (str) and returns:
    1. A list containing metadatas: (description, value) if asDict is False.
       If asDict is True, returns metadatas as an OrderedDict. Be aware that if multiple metadatas have the same description
       (which is stupid, but hey), they will be lost except the last one.
    2. The body of the file
    @param text: the content of the file
    @return: (list, str) or (OrderedDict, str)
    """
    md = []
    mdd = OrderedDict()
    body = []
    descr = ""
    val = ""
    inBody = False
    for s in text.split("\n"):
        if not inBody:
            m = re.match(r"^([^\s].*?):\s*(.*)$", s)
            if m:
                # Commit last metadata
                if descr:
                    if descr == "None":
                        descr = ""
                    md.append((descr, val))
                    mdd[descr] = val
                descr = ""
                val = ""

                # Store new values
                descr = m.group(1)
                val = m.group(2)

            elif s[:4] == "    ":
                val += "\n" + s.strip()

            elif s == "":
                # End of metadatas
                inBody = True

                # Commit last metadata
                if descr:
                    if descr == "None":
                        descr = ""
                    md.append((descr, val))
                    mdd[descr] = val

        else:
            body.append(s)

    # We remove the second empty line (since we save with two empty lines)
    if body and body[0] == "":
        body = body[1:]

    body = "\n".join(body)

    if not asDict:
        return md, body
    else:
        return mdd, body
