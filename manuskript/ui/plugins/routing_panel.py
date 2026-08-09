"""The panel that chooses which renderer produces each export format.

Every plugin with a page type needs this, so core owns the widget and fixes
it once for everyone. But core does not put it anywhere: the plugin details
pane belongs to the selected plugin, and drawing there uninvited is what
leaked one plugin's routing into another's panel. A plugin asks for this
through ``ui.export_routing`` and parents it wherever it likes.

Three states per row, and the point of having three is that none of them
lies:

* renderers that produce the format exactly -- a plain choice
* only renderers that produce a stand-in -- the choice says what actually
  comes out
* nothing at all -- unassigned, inert, with the formats that were searched
  named in the tooltip
"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QComboBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


#: Stored against a route to mean "no choice of mine; use the best there is".
AUTOMATIC = ""


class ExportRoutingPanel(QWidget):
    """Route one plugin's page type to every export format that takes it."""

    def __init__(
            self, routing, page_type_id, title="", intro="", parent=None):
        super().__init__(parent)
        self.routing = routing
        self.pageTypeId = page_type_id
        self._combos = {}
        self._syncing = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.titleLabel = QLabel(title, self)
        self.titleLabel.setWordWrap(True)
        self.titleLabel.setVisible(bool(title))
        layout.addWidget(self.titleLabel)

        self.introLabel = QLabel(
            intro or self.tr("Render these pages as…"),
            self,
        )
        self.introLabel.setWordWrap(True)
        layout.addWidget(self.introLabel)

        self.form = QFormLayout()
        self.form.setRowWrapPolicy(QFormLayout.WrapLongRows)
        self.form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        layout.addLayout(self.form)

        self.noticeLabel = QLabel(self)
        self.noticeLabel.setWordWrap(True)
        layout.addWidget(self.noticeLabel)

        self.optionsRow = QHBoxLayout()
        layout.addLayout(self.optionsRow)

        self.refresh()

    # ------------------------------------------------------------ building

    def refresh(self):
        self._syncing = True
        try:
            self._clear(self.form)
            self._combos = {}
            routes = self.routing.export_routes
            if not routes:
                self.noticeLabel.setText(
                    self.tr("No export format consumes these pages.")
                )
                self._build_option_buttons()
                return
            settled = {}
            for route in routes:
                renderer = self._settled_renderer(route)
                if renderer is not None:
                    # One renderer and no pin: there is no decision here,
                    # so it is summarised rather than given a row that
                    # looks like a choice.
                    settled.setdefault(
                        renderer.descriptor.id, (renderer, []),
                    )[1].append(route)
                    continue
                self.form.addRow(
                    self.tr(route.label),
                    self._field_for(route),
                )
            self.noticeLabel.setText(self._settled_summary(settled))
            self._build_option_buttons()
        finally:
            self._syncing = False

    def _settled_renderer(self, route):
        """The only renderer for a destination, when that is the whole story.

        Returns None when the row is worth showing: several renderers to
        pick between, an existing pin to be able to undo, or none at all.
        """
        candidates = self.routing.candidates(
            self.pageTypeId,
            route.representation_format,
        )
        if len(candidates) != 1:
            return None
        if self.routing.selected(self.pageTypeId, route.id):
            return None
        return candidates[0]

    def _settled_summary(self, settled):
        """One line per renderer that needs no choosing, listing where.

        Ten rows repeating one renderer's name told the reader there were
        ten decisions. There were none.
        """
        return "\n".join(
            self.tr("{}: {}").format(
                renderer.descriptor.name,
                ", ".join(self.tr(route.label) for route in routes),
            )
            for renderer, routes in settled.values()
        )

    def _field_for(self, route):
        candidates = self.routing.candidates(
            self.pageTypeId,
            route.representation_format,
        )
        if not candidates:
            return self._unassigned_field(route)
        return self._choice_field(route, candidates)

    def _unassigned_field(self, route):
        """Nothing produces this format, and nothing stands in for it.

        A legal state, not an error: a plugin may promise to consume a
        format no installed plugin provides yet.
        """
        label = QLabel(self.tr("Unassigned"), self)
        label.setEnabled(False)
        searched = self.routing.fallback_chain(
            route.representation_format
        )
        label.setToolTip(
            self.tr(
                "No installed renderer produces any of: {}"
            ).format(", ".join(searched))
        )
        return label

    def _choice_field(self, route, candidates):
        """The renderers for one destination, best first.

        With several candidates there is a real decision -- follow priority,
        or pin one -- so Automatic leads and names what it resolves to.

        With one candidate there is no decision to offer: pinning the only
        renderer available does exactly what following priority does. So the
        row states what will be produced and nothing is repeated. Install a
        second renderer and the choice appears.
        """
        combo = QComboBox(self)
        saved = self.routing.selected(self.pageTypeId, route.id)
        # A pin that already exists stays offered even when it is the only
        # renderer, or there would be no way left to clear it.
        if len(candidates) > 1 or saved:
            combo.addItem(
                self.tr("Automatic — {}").format(
                    candidates[0].descriptor.name,
                ),
                AUTOMATIC,
            )
            for renderer in candidates:
                combo.addItem(
                    self._describe(route, renderer),
                    renderer.descriptor.id,
                )
        else:
            combo.addItem(
                self._describe(route, candidates[0]),
                AUTOMATIC,
            )
        index = combo.findData(saved) if saved else 0
        combo.setCurrentIndex(index if index >= 0 else 0)
        combo.currentIndexChanged.connect(
            lambda _index, route=route: self._route_changed(route)
        )
        self._combos[route.id] = combo
        return combo

    def _describe(self, route, renderer):
        """A renderer's name, saying what it really produces if not the
        format asked for, and whose it is if not this plugin's.

        The Automatic entry deliberately does not use this: stacking "as
        Markdown" onto "Automatic — " produced three clauses and two
        dashes for what is one fact about one renderer.
        """
        label = renderer.descriptor.name
        wanted = route.representation_format
        if wanted not in renderer.target_formats:
            produced = next(
                (
                    media_type
                    for media_type in self.routing.fallback_chain(wanted)
                    if media_type in renderer.target_formats
                ),
                "",
            )
            if produced:
                label += self.tr(" — as {}").format(
                    self.routing.label_for(produced)
                )
        owner = self.routing.owner_of(renderer.descriptor.id)
        if owner and owner != self.routing.plugin_id:
            label += " — " + owner
        return label

    def _build_option_buttons(self):
        self._clear(self.optionsRow)
        seen = set()
        for route in self.routing.export_routes:
            for renderer in self.routing.candidates(
                    self.pageTypeId, route.representation_format):
                owner = self.routing.owner_of(renderer.descriptor.id)
                if owner != self.routing.plugin_id:
                    # Only this plugin's renderers are its to configure.
                    continue
                if renderer.descriptor.id in seen:
                    continue
                if not (
                    renderer.options or renderer.options_view_factory
                ):
                    continue
                seen.add(renderer.descriptor.id)
                button = QPushButton(
                    self.tr("Configure {}…").format(
                        renderer.descriptor.name
                    ),
                    self,
                )
                button.clicked.connect(
                    lambda _checked=False, renderer=renderer:
                    self.routing.edit_options(renderer, self)
                )
                self.optionsRow.addWidget(button)
        self.optionsRow.addStretch(1)

    # ------------------------------------------------------------- editing

    def _route_changed(self, route):
        if self._syncing:
            return
        combo = self._combos.get(route.id)
        if combo is None:
            return
        renderer_id = combo.currentData()
        try:
            self.routing.select(
                self.pageTypeId,
                route.id,
                renderer_id,
                representation_format=route.representation_format,
            )
        except Exception as error:
            self.routing.show_status(
                "Could not save that renderer: {}".format(error),
                8000,
                2,
            )
            return
        self.refresh()

    @staticmethod
    def _clear(layout):
        while layout.count():
            entry = layout.takeAt(0)
            widget = entry.widget()
            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()


class ExportRoutingService:
    """What a plugin receives from ``ui.export_routing``."""

    def __init__(self, gateway):
        self._gateway = gateway

    def panel(self, page_type_id, parent=None, title="", intro=""):
        """A panel routing one of this plugin's page types.

        Asking for somebody else's page type raises, because the gateway
        refuses it -- the scoping is the host's to enforce, not the
        panel's to respect.
        """
        self._gateway.require_owned(page_type_id)
        return ExportRoutingPanel(
            self._gateway,
            page_type_id,
            title=title,
            intro=intro,
            parent=parent,
        )

    @property
    def page_types(self):
        """This plugin's page types, so a panel can be built per type."""
        return self._gateway.page_types
