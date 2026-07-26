#!/usr/bin/env python
# --!-- coding: utf8 --!--

"""Integration tests for the exporter dialog."""

def test_export_dialog_loads_manager_and_restores_format(
        MWSampleProject):
    """
    Simply tests that export widget loads properly.
    """
    MW = MWSampleProject

    # Loading from mainWindow
    MW.doCompile()
    E = MW.dialog
    assert E.isVisible()
    available_formats = []
    for index in range(E.cmbExporters.count()):
        E.cmbExporters.setCurrentIndex(index)
        selected_exporter, selected_format = E.getSelectedExporter()
        if (
            selected_exporter
            and selected_format
            and selected_format.implemented
        ):
            available_formats.append(
                (
                    index,
                    selected_exporter.name,
                    selected_format.name,
                )
            )
    assert available_formats
    selected_index, exporter_name, format_name = (
        available_formats[-1]
    )
    E.cmbExporters.setCurrentIndex(selected_index)
    assert MW.applicationPreferences.last_exporter == exporter_name
    assert MW.applicationPreferences.last_export_format == format_name
    E.hide()

    # Load exporter manager
    E.openManager()
    EM = E.dialog
    assert EM.isVisible()
    EM.hide()

    EM.close()
    E.close()

    MW.doCompile()
    restored = MW.dialog
    selected_exporter, selected_format = (
        restored.getSelectedExporter()
    )
    assert selected_exporter.name == exporter_name
    assert selected_format.name == format_name
    restored.close()
