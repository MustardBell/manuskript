from PyQt5.QtCore import QModelIndex, Qt
from PyQt5.QtGui import QStandardItem, QStandardItemModel

from manuskript.enums import Character, Plot
from manuskript.models.characterModel import characterModel
from manuskript.models.persosProxyModel import persosProxyModel
from manuskript.models.plotsProxyModel import plotsProxyModel


def test_plot_proxy_preserves_names_while_grouping_by_importance():
    source = QStandardItemModel(0, len(Plot))
    for name, importance in (
        ("Minor plot", 0),
        ("Main plot", 2),
        ("Secondary plot", 1),
    ):
        row = [QStandardItem() for _ in Plot]
        row[Plot.name] = QStandardItem(name)
        row[Plot.importance] = QStandardItem(str(importance))
        source.appendRow(row)

    proxy = plotsProxyModel()
    proxy.setSourceModel(source)

    values = [
        proxy.data(proxy.index(row, Plot.name, QModelIndex()))
        for row in range(proxy.rowCount())
    ]

    assert values[1::2] == [
        "Main plot",
        "Secondary plot",
        "Minor plot",
    ]
    assert all(
        not proxy.mapToSource(proxy.index(row, 0)).isValid()
        for row in (0, 2, 4)
    )


def test_character_proxy_maps_custom_model_rows_without_item_api():
    source = characterModel(None)
    source.addCharacter(name="Minor character", importance=0)
    source.addCharacter(name="Main character", importance=2)

    proxy = persosProxyModel()
    proxy.setSourceModel(source)

    main_name = proxy.index(1, Character.name, QModelIndex())
    minor_name = proxy.index(4, Character.name, QModelIndex())

    assert proxy.data(main_name, Qt.DisplayRole) == "Main character"
    assert proxy.data(minor_name, Qt.DisplayRole) == "Minor character"
    assert proxy.mapToSource(main_name).row() == 1
    assert proxy.mapFromSource(source.index(0, 0)).row() == 4


def test_importance_proxy_rebuilds_when_importance_changes():
    source = characterModel(None)
    character = source.addCharacter(name="Moving character", importance=0)
    proxy = persosProxyModel()
    proxy.setSourceModel(source)

    source.setData(
        source.indexFromItem(character, Character.importance),
        2,
    )

    assert proxy.data(proxy.index(1, 0), Qt.DisplayRole) == (
        "Moving character"
    )
