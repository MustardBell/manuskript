#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""Tests for references.py"""

import pytest

def test_references(MWSampleProject):
    """
    Tests references using sample project.
    """
    from manuskript.models import references as Ref
    from manuskript.ui.reference_navigation import reference_navigation_for

    MW = MWSampleProject
    references = Ref.ReferenceService(
        Ref.ReferenceModels(
            outline=MW.mdlOutline,
            characters=MW.mdlCharacter,
            plots=MW.mdlPlots,
            world=MW.mdlWorld,
            statuses=MW.mdlStatus,
            labels=MW.mdlLabels,
        ),
        reference_navigation_for(MW),
    )

    # References
    ref1 = Ref.plotReference("42", searchable=True)
    ref2 = Ref.plotReference("42")
    assert ref1 in ref2

    ref1 = Ref.characterReference("42", searchable=True)
    ref2 = Ref.characterReference("42")
    assert ref1 in ref2

    ref1 = Ref.textReference("42", searchable=True)
    ref2 = Ref.textReference("42")
    assert ref1 in ref2

    ref1 = Ref.worldReference("42", searchable=True)
    ref2 = Ref.worldReference("42")
    assert ref1 in ref2

    # Plots
    mdlPlots = MW.mdlPlots
    plotsImp = mdlPlots.getPlotsByImportance()
    plots = []
    [plots.extend(i) for i in plotsImp]
    assert len(plots) == 3
    plotID = plots[0]
    assert "\n" in references.infos(Ref.plotReference(plotID))
    assert "Not a ref" in references.infos("<invalid>")
    assert "Unknown" in references.infos(Ref.plotReference("999"))
    assert references.short_infos(Ref.plotReference(plotID)) != None
    assert references.short_infos(Ref.plotReference("999")) == None
    assert references.short_infos("<invalidref>") == -1

    # Character
    mdlChar = MW.mdlCharacter
    IDs = [mdlChar.ID(r) for r in range(mdlChar.rowCount())]
    assert len(IDs) == 6  # Peter, Paul, Philip, Stephen, Barnabas, Herod
    charID = IDs[0]
    assert "\n" in references.infos(Ref.characterReference(charID))
    assert "Unknown" in references.infos(Ref.characterReference("999"))
    assert references.short_infos(Ref.characterReference(charID)) != None
    assert references.short_infos(Ref.characterReference("999")) == None
    assert references.short_infos("<invalidref>") == -1

    # Texts
    mdlOutline = MW.mdlOutline
    assert mdlOutline.rowCount() == 3  # Jerusalem, Samaria, Extremities
    root = mdlOutline.rootItem
    textID = root.child(0).ID()

    assert "\n" in references.infos(Ref.textReference(textID))
    assert "Unknown" in references.infos(Ref.textReference("999"))
    assert references.short_infos(Ref.textReference(textID)) != None
    assert references.short_infos(Ref.textReference("999")) == None
    assert references.short_infos("<invalidref>") == -1

    # World
    mdlWorld = MW.mdlWorld
    assert mdlWorld.rowCount() == 3  # Places, Culture, Travel
    worldID = mdlWorld.itemID(mdlWorld.item(2).child(1))

    assert "\n" in references.infos(Ref.worldReference(worldID))
    assert "Unknown" in references.infos(Ref.worldReference("999"))
    assert references.short_infos(Ref.worldReference(worldID)) != None
    assert references.short_infos(Ref.worldReference("999")) == None
    assert references.short_infos("<invalidref>") == -1

    refs = [Ref.plotReference(plotID),
            Ref.characterReference(charID),
            Ref.textReference(textID),
            Ref.worldReference(worldID),]

    # Titles
    for ref in refs:
        assert references.title(ref) != None
    assert references.title("<invalid>") == None
    assert references.title(Ref.plotReference("999")) == None

    # Other stuff
    assert references.reference_type(Ref.plotReference(plotID)) == Ref.PlotLetter
    assert references.reference_id(Ref.textReference(textID)) == textID
    assert "Unknown" in references.tooltip(Ref.worldReference("999"))
    assert "Not a ref" in references.tooltip("<invalid>")
    for ref in refs:
        assert references.tooltip(ref) != None

    # Links
    assert references.to_link("<invalid>") == None
    assert references.to_link(Ref.plotReference("999")) == Ref.plotReference("999")
    assert references.to_link(Ref.characterReference("999")) == Ref.characterReference("999")
    assert references.to_link(Ref.textReference("999")) == Ref.textReference("999")
    assert references.to_link(Ref.worldReference("999")) == Ref.worldReference("999")
    for ref in refs:
        assert "<a href" in references.to_link(ref)

    # Open
    assert references.open("<invalid>") == None
    assert references.open(Ref.plotReference("999")) == False
    assert references.open(Ref.characterReference("999")) == False
    assert references.open(Ref.textReference("999")) == False
    assert references.open(Ref.worldReference("999")) == False
    for ref in refs:
        assert references.open(ref) == True
    assert references.open(Ref.EmptyRef.format("Z", 14, "")) == False
