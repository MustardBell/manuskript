"""HTML presentation of references for tooltips and reference panels."""

import re

from PyQt5.QtWidgets import qApp

from manuskript.enums import Character
from manuskript.enums import Outline
from manuskript.enums import Plot
from manuskript.enums import PlotStep
from manuskript.functions import safeTranslate
from manuskript.models.references import (
    CharacterLetter,
    PlotLetter,
    ReferenceModels,
    TextLetter,
    WorldLetter,
    findReferencesTo,
    shortInfos,
)
from manuskript.models.reference_identity import (
    REFERENCE_PATTERN,
    ReferenceIdentity,
    character_reference,
    text_reference,
)


characterReference = character_reference
textReference = text_reference


###############################################################################
# READABLE INFOS
###############################################################################

def infos(ref, models):
    """Returns a full paragraph in HTML format
    containing detailed infos about the reference ``ref``.
    """
    identity = ReferenceIdentity.parse(ref)
    if identity is None:
        return safeTranslate(qApp, "references", "Not a reference: {}.").format(ref)

    _type = identity.kind
    _ref = identity.identifier

    # A text or outline item
    if _type == TextLetter:
        m = models.outline
        idx = m.getIndexByID(_ref)

        if not idx.isValid():
            return safeTranslate(qApp, "references", "Unknown reference: {}.").format(ref)

        item = idx.internalPointer()

        # Titles
        pathTitle = safeTranslate(qApp, "references", "Path:")
        statsTitle = safeTranslate(qApp, "references", "Stats:")
        POVTitle = safeTranslate(qApp, "references", "POV:")
        statusTitle = safeTranslate(qApp, "references", "Status:")
        labelTitle = safeTranslate(qApp, "references", "Label:")
        ssTitle = safeTranslate(qApp, "references", "Short summary:")
        lsTitle = safeTranslate(qApp, "references", "Long summary:")
        notesTitle = safeTranslate(qApp, "references", "Notes:")

        # The POV of the scene
        POV = ""
        if item.POV():
            POV = "<a href='{ref}'>{text}</a>".format(
                    ref=characterReference(item.POV()),
                    text=models.characters.getCharacterByID(item.POV()).name())

        # The status of the scene
        status = item.status()
        if status:
            status = models.statuses.item(int(status), 0).text()
        else:
            status = ""

        # The label of the scene
        label = item.label()
        if label:
            label = models.labels.item(int(label), 0).text()
        else:
            label = ""

        # The path of the scene
        path = item.pathID()
        pathStr = []
        for _id, title in path:
            pathStr.append("<a href='{ref}'>{text}</a>".format(
                    ref=textReference(_id),
                    text=title))
        path = " > ".join(pathStr)

        # Summaries and notes
        ss = item.data(Outline.summarySentence)
        ls = item.data(Outline.summaryFull)
        notes = item.data(Outline.notes)

        text = """<h1>{title}</h1>
        <p><b>{pathTitle}</b> {path}</p>
        <p><b>{statsTitle}</b> {stats}<br>
            {POV}
            {status}
            {label}</p>
        {ss}
        {ls}
        {notes}
        {references}
        """.format(
                title=item.title(),
                pathTitle=pathTitle,
                path=path,
                statsTitle=statsTitle,
                stats=item.stats(),
                POV="<b>{POVTitle}</b> {POV}<br>".format(
                        POVTitle=POVTitle,
                        POV=POV) if POV else "",
                status="<b>{statusTitle}</b> {status}<br>".format(
                        statusTitle=statusTitle,
                        status=status) if status else "",
                label="<b>{labelTitle}</b> {label}</p>".format(
                        labelTitle=labelTitle,
                        label=label) if label else "",
                ss="<p><b>{ssTitle}</b> {ss}</p>".format(
                        ssTitle=ssTitle,
                        ss=ss.replace("\n", "<br>")) if ss.strip() else "",
                ls="<p><b>{lsTitle}</b><br>{ls}</p>".format(
                        lsTitle=lsTitle,
                        ls=ls.replace("\n", "<br>")) if ls.strip() else "",
                notes="<p><b>{notesTitle}</b><br>{notes}</p>".format(
                        notesTitle=notesTitle,
                        notes=linkifyAllRefs(notes, models)) if notes.strip() else "",
                references=listReferences(ref, models)
        )

        return text

    # A character
    elif _type == CharacterLetter:
        m = models.characters
        c = m.getCharacterByID(int(_ref))
        if c == None:
            return safeTranslate(qApp, "references", "Unknown reference: {}.").format(ref)

        index = c.index()

        name = c.name()

        # Titles
        basicTitle = safeTranslate(qApp, "references", "Basic info")
        detailedTitle = safeTranslate(qApp, "references", "Detailed info")
        POVof = safeTranslate(qApp, "references", "POV of:")

        # Goto (link)
        goto = safeTranslate(qApp, "references", "Go to {}.")
        goto = goto.format(refToLink(ref, models))

        # basic infos
        basic = []
        for i in [
            (Character.motivation, safeTranslate(qApp, "references", "Motivation"), False),
            (Character.goal, safeTranslate(qApp, "references", "Goal"), False),
            (Character.conflict, safeTranslate(qApp, "references", "Conflict"), False),
            (Character.epiphany, safeTranslate(qApp, "references", "Epiphany"), False),
            (Character.summarySentence, safeTranslate(qApp, "references", "Short summary"), True),
            (Character.summaryPara, safeTranslate(qApp, "references", "Longer summary"), True),
        ]:

            val = m.data(index.sibling(index.row(), i[0].value))

            if val:
                basic.append("<b>{title}:</b>{n}{val}".format(
                        title=i[1],
                        n="\n" if i[2] else " ",
                        val=val))
        basic = "<br>".join(basic)

        # detailed infos
        detailed = []
        for _name, _val in c.listInfos():
            detailed.append("<b>{}:</b> {}".format(
                    _name,
                    _val))
        detailed = "<br>".join(detailed)

        # list scenes of which it is POV
        oM = models.outline
        lst = oM.findItemsByPOV(_ref)

        listPOV = ""
        for t in lst:
            idx = oM.getIndexByID(t)
            listPOV += "<li><a href='{link}'>{text}</a></li>".format(
                    link=textReference(t),
                    text=oM.data(idx, Outline.title))

        text = """<h1>{name}</h1>
        {goto}
        {basicInfos}
        {detailedInfos}
        {POV}
        {references}
        """.format(
                name=name,
                goto=goto,
                basicInfos="<h2>{basicTitle}</h2>{basic}".format(
                        basicTitle=basicTitle,
                        basic=basic) if basic else "",
                detailedInfos="<h2>{detailedTitle}</h2>{detailed}".format(
                        detailedTitle=detailedTitle,
                        detailed=detailed) if detailed else "",
                POV="<h2>{POVof}</h2><ul>{listPOV}</ul>".format(
                        POVof=POVof,
                        listPOV=listPOV) if listPOV else "",
                references=listReferences(ref, models)
        )
        return text

    # A plot
    elif _type == PlotLetter:
        m = models.plots
        index = m.getIndexFromID(_ref)
        name = m.getPlotNameByID(_ref)

        if not index.isValid():
            return safeTranslate(qApp, "references", "Unknown reference: {}.").format(ref)

        # Titles
        descriptionTitle = safeTranslate(qApp, "references", "Description")
        resultTitle = safeTranslate(qApp, "references", "Result")
        charactersTitle = safeTranslate(qApp, "references", "Characters")
        stepsTitle = safeTranslate(qApp, "references", "Resolution steps")

        # Goto (link)
        goto = safeTranslate(qApp, "references", "Go to {}.")
        goto = goto.format(refToLink(ref, models))

        # Description
        description = m.data(index.sibling(index.row(),
                                           Plot.description))

        # Result
        result = m.data(index.sibling(index.row(),
                                      Plot.result))

        # Characters
        pM = models.characters
        item = m.item(index.row(), Plot.characters)
        characters = ""
        if item:
            for r in range(item.rowCount()):
                ID = item.child(r, 0).text()
                character = pM.getCharacterByID(ID)

                if character is not None:
                    characters += "<li><a href='{link}'>{text}</a>".format(
                            link=characterReference(ID),
                            text=character.name())

        # Resolution steps
        steps = ""
        item = m.item(index.row(), Plot.steps)
        if item:
            for r in range(item.rowCount()):
                title = item.child(r, PlotStep.name).text()
                summary = item.child(r, PlotStep.summary).text()
                meta = item.child(r, PlotStep.meta).text()
                if meta:
                    meta = " <span style='color:gray;'>({})</span>".format(meta)
                steps += "<li><b>{title}</b>{summary}{meta}</li>".format(
                        title=title,
                        summary=": {}".format(summary) if summary else "",
                        meta=meta if meta else "")

        text = """<h1>{name}</h1>
        {goto}
        {characters}
        {description}
        {result}
        {steps}
        {references}
        """.format(
                name=name,
                goto=goto,
                description="<h2>{title}</h2>{text}".format(
                        title=descriptionTitle,
                        text=description) if description else "",
                result="<h2>{title}</h2>{text}".format(
                        title=resultTitle,
                        text=result) if result else "",
                characters="<h2>{title}</h2><ul>{lst}</ul>".format(
                        title=charactersTitle,
                        lst=characters) if characters else "",
                steps="<h2>{title}</h2><ul>{steps}</ul>".format(
                        title=stepsTitle,
                        steps=steps) if steps else "",
                references=listReferences(ref, models)
        )
        return text

    # A World item
    elif _type == WorldLetter:
        m = models.world
        index = m.indexByID(_ref)
        name = m.name(index)

        if not index.isValid():
            return safeTranslate(qApp, "references", "Unknown reference: {}.").format(ref)

        # Titles
        descriptionTitle = safeTranslate(qApp, "references", "Description")
        passionTitle = safeTranslate(qApp, "references", "Passion")
        conflictTitle = safeTranslate(qApp, "references", "Conflict")

        # Goto (link)
        goto = safeTranslate(qApp, "references", "Go to {}.")
        goto = goto.format(refToLink(ref, models))

        # Description
        description = basicFormat(m.description(index), models)

        # Passion
        passion = basicFormat(m.passion(index), models)

        # Conflict
        conflict = basicFormat(m.conflict(index), models)

        text = """<h1>{name}</h1>
        {goto}
        {description}
        {passion}
        {conflict}
        {references}
        """.format(
                name=name,
                goto=goto,
                description="<h2>{title}</h2>{text}".format(
                        title=descriptionTitle,
                        text=description) if description else "",
                passion="<h2>{title}</h2>{text}".format(
                        title=passionTitle,
                        text=passion) if passion else "",
                conflict="<h2>{title}</h2><ul>{lst}</ul>".format(
                        title=conflictTitle,
                        lst=conflict) if conflict else "",
                references=listReferences(ref, models)
        )
        return text

    else:
        return safeTranslate(qApp, "references", "Unknown reference: {}.").format(ref)


def tooltip(ref, models):
    """Returns a tooltip in HTML for the reference ``ref``."""
    infos = shortInfos(ref, models)

    if not infos:
        return safeTranslate(qApp, "references", "<b>Unknown reference:</b> {}.").format(ref)

    if infos == -1:
        return safeTranslate(qApp, "references", "Not a reference: {}.").format(ref)

    if infos["type"] == TextLetter:
        if infos["text_type"] == "folder":
            tt = safeTranslate(qApp, "references", "Folder: <b>{}</b>").format(infos["title"])
        else:
            tt = safeTranslate(qApp, "references", "Text: <b>{}</b>").format(infos["title"])
        tt += "<br><i>{}</i>".format(infos["path"])
        return tt

    elif infos["type"] == CharacterLetter:
        return safeTranslate(qApp, "references", "Character: <b>{}</b>").format(infos["title"])

    elif infos["type"] == PlotLetter:
        return safeTranslate(qApp, "references", "Plot: <b>{}</b>").format(infos["title"])

    elif infos["type"] == WorldLetter:
        return safeTranslate(qApp, "references", "World: <b>{name}</b>{path}").format(
                    name=infos["title"],
                    path=" <span style='color:gray;'>({})</span>".format(infos["path"]) if infos["path"] else "")


###############################################################################
# FUNCTIONS
###############################################################################

def refToLink(ref, models):
    """Transforms the reference ``ref`` in a link displaying useful infos
    about that reference. For character, character's name. For text item,
    item's name, etc.
    """
    identity = ReferenceIdentity.parse(ref)
    if identity is not None:
        _type = identity.kind
        _ref = identity.identifier
        text = ""
        if _type == TextLetter:
            m = models.outline
            idx = m.getIndexByID(_ref)
            if idx.isValid():
                item = idx.internalPointer()
                text = item.title()

        elif _type == CharacterLetter:
            m = models.characters
            c = m.getCharacterByID(int(_ref))
            if c:
                text = c.name()

        elif _type == PlotLetter:
            m = models.plots
            text = m.getPlotNameByID(_ref)

        elif _type == WorldLetter:
            m = models.world
            item = m.itemByID(_ref)
            if item:
                text = item.text()

        if text:
            return "<a href='{ref}'>{text}</a>".format(
                    ref=ref,
                    text=text)
        else:
            return ref

def linkifyAllRefs(text, models):
    """Takes all the references in ``text`` and transform them into HMTL links."""
    return re.sub(
        REFERENCE_PATTERN,
        lambda match: refToLink(match.group(0), models),
        text,
    )

def listReferences(ref, models, title=None):
    if title is None:
        title = safeTranslate(qApp, "references", "Referenced in:")
    oM = models.outline
    listRefs = ""

    lst = findReferencesTo(ref, models)

    for t in lst:
        idx = oM.getIndexByID(t)
        listRefs += "<li><a href='{link}'>{text}</a></li>".format(
                link=textReference(t),
                text=oM.data(idx, Outline.title))

    return "<h2>{title}</h2><ul>{ref}</ul>".format(
            title=title,
            ref=listRefs) if listRefs else ""

def basicFormat(text, models):
    if not text:
        return ""
    text = text.replace("\n", "<br>")
    text = linkifyAllRefs(text, models)
    return text


class ReferenceHtmlPresenter:
    """Render one project's resolved references for rich-text Qt views."""

    def __init__(self, models: ReferenceModels):
        self.models = models

    def infos(self, ref):
        return infos(ref, self.models)

    def tooltip(self, ref):
        return tooltip(ref, self.models)

    def to_link(self, ref):
        return refToLink(ref, self.models)

    def linkify_all(self, text):
        return linkifyAllRefs(text, self.models)

    def list_references(self, ref, title=None):
        return listReferences(ref, self.models, title=title)

    def basic_format(self, text):
        return basicFormat(text, self.models)
