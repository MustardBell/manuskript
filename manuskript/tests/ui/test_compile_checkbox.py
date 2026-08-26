"""Compile controls operate on effective hierarchical inclusion."""

from PyQt5.QtCore import Qt

from manuskript.enums import Outline
from manuskript.models.outlineItem import outlineItem
from manuskript.ui.views.chkOutlineCompile import chkOutlineCompile


def compile_index(model, item):
    return model.indexFromItem(item, Outline.compile)


def outline_branch(window):
    model = window.projectRuntime.models.outline
    folder = outlineItem(title="Folder", parent=model.rootItem)
    child = outlineItem(title="Child", _type="md", parent=folder)
    direct = outlineItem(title="Direct", _type="md", parent=model.rootItem)
    return model, folder, child, direct


def test_checking_an_inherited_exclusion_makes_the_branch_compilable(
        MWEmptyProject):
    model, folder, document, _direct = outline_branch(MWEmptyProject)
    folder.setData(Outline.compile, Qt.Unchecked)
    assert document.data(Outline.compile) == Qt.Checked
    assert not document.compile()
    checkbox = chkOutlineCompile()
    checkbox.setModel(model)
    checkbox.setCurrentModelIndex(compile_index(model, document))
    assert checkbox.accessibleName() == "Compile"
    assert "parent folders" in checkbox.toolTip()
    assert checkbox.checkState() == Qt.Unchecked
    # Merely presenting the inherited answer must not erase the child's
    # retained local inclusion.
    assert document.data(Outline.compile) == Qt.Checked

    checkbox.click()

    assert folder.compile()
    assert document.compile()
    assert checkbox.checkState() == Qt.Checked


def test_native_model_check_role_uses_the_same_hierarchical_command(
        MWEmptyProject):
    model, folder, document, _direct = outline_branch(MWEmptyProject)
    folder.setData(Outline.compile, Qt.Unchecked)

    model.setData(
        compile_index(model, document),
        Qt.Checked,
        Qt.CheckStateRole,
    )

    assert folder.compile()
    assert document.compile()


def test_unchecking_then_rechecking_a_direct_item_remains_symmetric(
        MWEmptyProject):
    model, _folder, _child, document = outline_branch(MWEmptyProject)
    checkbox = chkOutlineCompile()
    checkbox.setModel(model)
    checkbox.setCurrentModelIndex(compile_index(model, document))
    assert checkbox.checkState() == Qt.Checked

    checkbox.click()
    assert not document.compile()
    assert checkbox.checkState() == Qt.Unchecked

    checkbox.click()
    assert document.compile()
    assert checkbox.checkState() == Qt.Checked


def test_including_an_inherited_item_survives_save_and_reopen(
        MWNoProject, tmp_path):
    window = MWNoProject
    project_file = tmp_path / "compile-roundtrip.msk"
    window.welcome.createFile(str(project_file), overwrite=True)
    model, folder, document, _direct = outline_branch(window)
    folder_id = folder.ID()
    document_id = document.ID()
    folder.setData(Outline.compile, Qt.Unchecked)
    checkbox = chkOutlineCompile()
    checkbox.setModel(model)
    checkbox.setCurrentModelIndex(compile_index(model, document))

    checkbox.click()
    assert window.projectManager.saveDatas()
    assert window.projectManager.closeProject()
    assert window.projectManager.loadProject(str(project_file))

    loaded = window.projectRuntime.models.outline
    loaded_folder = loaded.getItemByID(folder_id)
    loaded_document = loaded.getItemByID(document_id)
    assert loaded_folder.compile()
    assert loaded_document.compile()
