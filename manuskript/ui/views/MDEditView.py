#!/usr/bin/env python
# --!-- coding: utf8 --!--

import html
import re

from PyQt5.QtCore import (
    QRegExp,
    Qt,
    QTimer,
    QRect,
    QPoint,
    pyqtSignal,
)
from PyQt5.QtGui import QTextCursor
from PyQt5.QtWidgets import qApp, QMenu, QToolTip

from manuskript.ui.views.textEditView import textEditView
from manuskript.ui.highlighters import MarkdownHighlighter
from manuskript.ui.highlighters import BasicHighlighter
from manuskript.ui.highlighters.markdownEnums import MarkdownState as MS
from manuskript.ui.highlighters.markdownTokenizer import MarkdownTokenizer as MT
from manuskript.ui.editors.markdownInlineFormatting import (
    plan_inline_markup_toggle,
)
from manuskript.ui.editors.markdownPresentation import (
    MarkdownPresentationMode,
)
from manuskript.ui.plugins.markup_profiles import MARKDOWN_BASE_ID
from manuskript.plugins.api import RenderedDocument
from manuskript.plugins.execution import run_page_renderer
from manuskript import functions as F

import logging
LOGGER = logging.getLogger(__name__)

class MDEditView(textEditView):

    presentationModeChanged = pyqtSignal(object)
    wikilinkActivated = pyqtSignal(str)

    blockquoteRegex = QRegExp("^ {0,3}(>\\s*)+")
    listRegex = QRegExp(r"^(\s*)([+*-]|([0-9a-z])+([.\)]))(\s+)")
    inlineLinkRegex = QRegExp("\\[([^\n]+)\\]\\(([^\n]+)\\)")
    imageRegex = QRegExp("!\\[([^\n]*)\\]\\(([^\n]+)\\)")
    automaticLinkRegex = QRegExp("(<([a-zA-Z]+\\:[^\n]+)>)|(<([^\n]+@[^\n]+)>)")
    wikilinkRegex = QRegExp(
        "\\[\\[([^\\]|]+)(\\|([^\\]]+))?\\]\\]"
    )

    def __init__(self, parent=None, index=None, html=None, spellcheck=None,
                 highlighting=False, dict="", autoResize=False,
                 settings=None):
        self._noFocusMode = False
        self._lastCursorPosition = None
        self._presentationState = None
        self._presentationHost = None
        self._highlighterSuspendedForReading = False
        self._contentReadOnly = html is not None
        self._editingLocked = False
        self._markupProfileState = None
        self._pageTypeState = None
        self._markupBaseId = MARKDOWN_BASE_ID
        self._markupBehaviors = ()
        self._readingRenderer = None
        self._wikilinkCompletionRange = None
        self._wikilinkCompletionMenu = None
        textEditView.__init__(self, parent, index, html, spellcheck,
                              highlighting=True, dict=dict,
                              autoResize=autoResize, settings=settings,
                              highlighter_class=MarkdownHighlighter)

        # Re-highlighting a document can emit hundreds of layout changes.
        # Rebuild interactive link geometry once after those changes settle,
        # rather than rescanning the complete document for every block.
        self.clickRects = []
        self.interactionRectUpdateTimer = QTimer(self)
        self.interactionRectUpdateTimer.setSingleShot(True)
        self.interactionRectUpdateTimer.setInterval(0)
        self.interactionRectUpdateTimer.timeout.connect(
            self.updateInteractionRects
        )

        # Highlighter
        self._textFormat = "md"
        self.readingView = None
        self._presentationMode = (
            MarkdownPresentationMode.FORMATTED_SOURCE
        )
        self._applyPresentationMode()

        if index:
            # We have to setup things anew, for the highlighter notably
            self.setCurrentModelIndex(index)

        self.cursorPositionChanged.connect(self.cursorPositionHasChanged)
        self.wikilinkActivated.connect(self._openWikilink)
        self.verticalScrollBar().rangeChanged.connect(
            self.scrollBarRangeChanged)

        # Clickable things
        self.textChanged.connect(self.scheduleInteractionRectUpdate)
        self.document().documentLayoutChanged.connect(
            self.scheduleInteractionRectUpdate
        )
        self.setMouseTracking(True)
        self.scheduleInteractionRectUpdate()

    @property
    def presentationMode(self):
        return self._presentationMode

    def setPresentationMode(self, mode):
        mode = MarkdownPresentationMode.from_value(mode)
        if (
            not self._contentReadOnly
            and mode is MarkdownPresentationMode.READING
            and self._presentationHost is None
        ):
            raise RuntimeError(
                "Reading mode requires a MarkdownEditorHost"
            )
        if mode is self._presentationMode:
            self._applyPresentationMode()
            return

        self._presentationMode = mode
        self._applyPresentationMode()
        self.presentationModeChanged.emit(mode)

    def _applyPresentationMode(self):
        reading_active = (
            not self._contentReadOnly
            and self._presentationMode
            is MarkdownPresentationMode.READING
        )
        self.setReadOnly(
            self._contentReadOnly
            or self._editingLocked
            or not self._presentationMode.is_editable
        )
        if reading_active and self._presentationHost is None:
            raise RuntimeError(
                "Reading mode requires a MarkdownEditorHost"
            )
        effective_mode = (
            self._presentationMode
            if not self._contentReadOnly
            else MarkdownPresentationMode.FORMATTED_SOURCE
        )
        active_sibling = (
            self._presentationHost.setPresentationMode(effective_mode)
            if self._presentationHost is not None
            else None
        )
        self._setHighlighterSuspended(
            active_sibling is not None
        )
        if self.highlighter and active_sibling is None:
            self.highlighter.rehighlight()

    @property
    def editingLocked(self):
        return self._editingLocked

    def setEditingLocked(self, locked):
        """Lock source editing without changing presentation semantics."""
        locked = bool(locked)
        if locked == self._editingLocked:
            return
        if locked and not self.isReadOnly():
            self.submit()
        self._editingLocked = locked
        self._applyPresentationMode()

    def setPresentationHost(self, host):
        if (
            self._presentationHost is not None
            and self._presentationHost is not host
        ):
            raise RuntimeError(
                "A Markdown editor can belong to only one presentation host"
            )
        self._presentationHost = host
        host.setReadingRenderer(self._readingRenderer)
        if self.styleSheet():
            host.setStyleSheet(self.styleSheet())
            self.setStyleSheet("")
        self._applyPresentationMode()

    def _setHighlighterSuspended(self, suspended):
        if not self.highlighter:
            return
        if (
            suspended
            and not self._highlighterSuspendedForReading
        ):
            self.highlighter.setDocument(None)
            self._highlighterSuspendedForReading = True
        elif (
            not suspended
            and self._highlighterSuspendedForReading
        ):
            self.highlighter.setDocument(self.document())
            self._highlighterSuspendedForReading = False

    def setPresentationState(self, state):
        """Attach this view to its owning editor leaf's presentation state."""
        if self._presentationState is not None:
            try:
                self._presentationState.modeChanged.disconnect(
                    self.setPresentationMode
                )
            except (RuntimeError, TypeError):
                pass

        self._presentationState = state
        if state is not None:
            state.modeChanged.connect(self.setPresentationMode)
            self.setPresentationMode(state.mode)
        else:
            self.setPresentationMode(
                MarkdownPresentationMode.FORMATTED_SOURCE
            )

    def setMarkupProfileState(self, state):
        if self._markupProfileState is not None:
            try:
                self._markupProfileState.changed.disconnect(
                    self._applyMarkupProfile
                )
            except (RuntimeError, TypeError):
                pass
        self._markupProfileState = state
        if state is not None:
            state.changed.connect(self._applyMarkupProfile)
        self._applyMarkupProfile()

    def setPageTypeState(self, state):
        if self._pageTypeState is not None:
            try:
                self._pageTypeState.changed.disconnect(
                    self._applyPageType
                )
            except (RuntimeError, TypeError):
                pass
        self._pageTypeState = state
        if state is not None:
            state.changed.connect(self._applyPageType)
        self._applyPageType()

    def _applyMarkupProfile(self):
        state = self._markupProfileState
        self._markupBaseId = (
            state.base_id if state is not None else MARKDOWN_BASE_ID
        )
        base_contribution = (
            state.base_contribution if state is not None else None
        )
        if base_contribution is None:
            self._installHighlighter(
                lambda editor: MarkdownHighlighter(editor),
                contribution=None,
            )
        else:
            self._installHighlighter(
                base_contribution.highlighter_factory,
                contribution=base_contribution,
            )

        extensions = []
        behaviors = []
        contributions = (
            state.additive_contributions
            if state is not None
            else ()
        )
        for contribution in contributions:
            try:
                extension = contribution.highlighter_factory(self)
                if not callable(
                    getattr(extension, "highlight_block", None)
                ):
                    raise TypeError(
                        "Additive highlighter factories must return "
                        "objects with highlight_block(highlighter, text)."
                    )
                extensions.append(
                    _PluginHighlightGuard(
                        contribution,
                        extension,
                        self._reportMarkupError,
                    )
                )
            except Exception as error:
                self._reportMarkupError(contribution, error)
            behavior = self._createMarkupBehavior(contribution)
            if behavior is not None:
                behaviors.append(behavior)

        if base_contribution is not None:
            behavior = self._createMarkupBehavior(base_contribution)
            if behavior is not None:
                behaviors.insert(0, behavior)
        self._markupBehaviors = tuple(behaviors)
        if isinstance(self.highlighter, MarkdownHighlighter):
            self.highlighter.setPluginExtensions(extensions)
        self.scheduleInteractionRectUpdate()

    def _applyPageType(self):
        state = self._pageTypeState
        wizard_contribution = (
            state.contribution
            if state is not None
            and state.contribution is not None
            and state.contribution.wizard_factory is not None
            else None
        )
        renderer_contribution = (
            state.contribution
            if state is not None
            and state.contribution is not None
            and state.contribution.renderer_factory is not None
            else None
        )
        self._readingRenderer = (
            _PluginReadingRendererGuard(
                renderer_contribution,
                self._reportPageTypeError,
            )
            if renderer_contribution is not None
            else None
        )
        if self._presentationHost is not None:
            self._presentationHost.setReadingRenderer(
                self._readingRenderer
            )
            self._presentationHost.setPageWizardFactory(
                (
                    wizard_contribution.wizard_factory
                    if wizard_contribution is not None
                    else None
                ),
                error_handler=(
                    lambda error, contribution=wizard_contribution:
                    self._reportPageTypeError(contribution, error)
                    if contribution is not None
                    else None
                ),
            )

    def _installHighlighter(self, factory, contribution):
        old = self.highlighter
        if old is not None:
            old.setDocument(None)
            old.deleteLater()
        try:
            highlighter = factory(self)
            if not isinstance(highlighter, BasicHighlighter):
                raise TypeError(
                    "Replacement highlighter factories must return "
                    "BasicHighlighter instances."
                )
        except Exception as error:
            if contribution is not None:
                self._reportMarkupError(contribution, error)
            highlighter = BasicHighlighter(self)
        self.highlighter = highlighter
        highlighter.setDefaultBlockFormat(self._defaultBlockFormat)
        highlighter.setDefaultCharFormat(self._defaultCharFormat)
        highlighter.updateColorScheme(rehighlight=False)
        if self._highlighterSuspendedForReading:
            highlighter.setDocument(None)
        else:
            highlighter.rehighlight()

    def _createMarkupBehavior(self, contribution):
        if contribution.behavior_factory is None:
            return None
        try:
            behavior = contribution.behavior_factory(self)
            if not any(
                callable(getattr(behavior, method, None))
                for method in (
                    "key_press_event",
                    "command",
                    "plain_text",
                )
            ):
                raise TypeError(
                    "Markup behavior factories must return objects with "
                    "editor behavior methods."
                )
            return _PluginBehaviorGuard(
                contribution,
                behavior,
                self._reportMarkupError,
            )
        except Exception as error:
            self._reportMarkupError(contribution, error)
            return None

    def _reportMarkupError(self, contribution, error):
        state = self._markupProfileState
        if state is not None:
            state.service.report_error(contribution, error)

    def _reportPageTypeError(self, contribution, error):
        state = self._pageTypeState
        if state is not None:
            state.service.report_error(contribution, error)

    def _dispatchMarkupCommand(self, command, *arguments):
        for behavior in self._markupBehaviors:
            if behavior.command(self, command, *arguments):
                return True
        return self._markupBaseId != MARKDOWN_BASE_ID

    def _pluginPlainText(self, text, remove_comments):
        for behavior in self._markupBehaviors:
            value = behavior.plain_text(
                self,
                text,
                remove_comments=remove_comments,
            )
            if value is not None:
                return str(value)
        return None

    def setupEditorForIndex(self, index):
        textEditView.setupEditorForIndex(self, index)
        if self._markupProfileState is not None:
            self._applyMarkupProfile()

    def set_text_editor_context(self, context):
        textEditView.set_text_editor_context(self, context)

    def wikilinkCompletions(self, prefix):
        provider = getattr(
            self.text_editor_context, "complete_wikilink", None
        )
        return tuple(provider(prefix)) if provider is not None else ()

    def _openWikilink(self, target):
        command = getattr(self.text_editor_context, "open_wikilink", None)
        return bool(command(target)) if command is not None else False

    def buildWikilinkCompletionMenu(self):
        """Build an accessible completion menu for the current target."""

        completion = self._wikilinkTargetAtCursor()
        if completion is None:
            return None
        start, end, prefix = completion
        suggestions = self.wikilinkCompletions(prefix)
        if not suggestions:
            return None

        menu = QMenu(self)
        menu.setObjectName("wikilinkCompletionMenu")
        for suggestion in suggestions[:50]:
            label = suggestion.title
            if suggestion.target != suggestion.title:
                label = "{} — {}".format(label, suggestion.target)
            action = menu.addAction(label)
            action.setData(suggestion.target)
            action.setStatusTip(
                self.tr("Insert reference to {}").format(suggestion.target)
            )
            action.triggered.connect(
                lambda _checked=False, target=suggestion.target:
                    self._insertWikilinkCompletion(target)
            )
        self._wikilinkCompletionRange = (start, end)
        self._wikilinkCompletionMenu = menu
        return menu

    def showWikilinkCompletions(self):
        menu = self.buildWikilinkCompletionMenu()
        if menu is None:
            return False
        menu.popup(self.mapToGlobal(self.cursorRect().bottomLeft()))
        return True

    def _wikilinkTargetAtCursor(self):
        cursor = self.textCursor()
        block = cursor.block()
        if block.userState() in (
            MS.MarkdownStateCodeBlock,
            MS.MarkdownStateInGithubCodeFence,
            MS.MarkdownStateInPandocCodeFence,
            MS.MarkdownStateCodeFenceEnd,
        ):
            return None
        position = cursor.position() - block.position()
        before = block.text()[:position]
        opening = before.rfind("[[")
        if opening < 0 or "|" in before[opening + 2:]:
            return None
        slashes = 0
        escaped_at = opening - 1
        while escaped_at >= 0 and before[escaped_at] == "\\":
            slashes += 1
            escaped_at -= 1
        if slashes % 2:
            return None
        if any(
            span.start <= opening < span.end
            for span in self.highlighter.dslParser.excluded_spans(
                block.text()
            )
        ):
            return None
        prefix = before[opening + 2:]
        if any(character in prefix for character in "[]\n"):
            return None
        return (
            block.position() + opening + 2,
            cursor.position(),
            prefix,
        )

    def _insertWikilinkCompletion(self, target):
        if self._wikilinkCompletionRange is None:
            return
        start, end = self._wikilinkCompletionRange
        cursor = QTextCursor(self.document())
        cursor.setPosition(start)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.insertText(str(target))
        target_end = cursor.position()
        following = self.toPlainText()[target_end:target_end + 2]
        if following != "]]":
            cursor.insertText("]]")
        cursor.setPosition(target_end)
        self.setTextCursor(cursor)
        self._wikilinkCompletionRange = None

    ###########################################################################
    # KEYPRESS
    ###########################################################################

    def keyPressEvent(self, event):
        for behavior in self._markupBehaviors:
            if behavior.key_press_event(self, event):
                return
        if self._markupBaseId != MARKDOWN_BASE_ID:
            textEditView.keyPressEvent(self, event)
            return

        if (
            event.modifiers() == Qt.ControlModifier
            and event.key() == Qt.Key_Space
            and self.showWikilinkCompletions()
        ):
            return

        k = event.key()
        m = event.modifiers()
        cursor = self.textCursor()

        # RETURN
        if k == Qt.Key_Return:
            if not cursor.hasSelection():
                if m & Qt.ShiftModifier:
                    # Insert Markdown-style line break
                    cursor.insertText("  ")

                if m & Qt.ControlModifier:
                    cursor.insertText("\n")
                else:
                    self.handleCarriageReturn()
            else:
                textEditView.keyPressEvent(self, event)

        # TAB
        elif k == Qt.Key_Tab:
            self.indentText()
        elif k == Qt.Key_Backtab:
            self.unindentText()

        else:
            textEditView.keyPressEvent(self, event)

    # Thanks to GhostWriter, mainly
    def handleCarriageReturn(self):
        autoInsertText = "";
        cursor = self.textCursor()
        endList = False
        moveBack = False
        text = cursor.block().text()

        if cursor.positionInBlock() < cursor.block().length() - 1:
            autoInsertText = self.getPriorIndentation()
            if cursor.positionInBlock() < len(autoInsertText):
                autoInsertText = autoInsertText[:cursor.positionInBlock()]

        else:
            s = cursor.block().userState()

            if s in [MS.MarkdownStateNumberedList,
                     MS.MarkdownStateBulletPointList]:
                self.listRegex.indexIn(text)
                g = self.listRegex.capturedTexts()
                    # 0 = "   a. " or "  * "
                    # 1 = "   "       "  "
                    # 2 =    "a."       "*"
                    # 3 =    "a"          ""
                    # 4 =     "."         ""
                    # 5 =      " "        " "

                # If the line of text is an empty list item, end the list.
                if len(g[0].strip()) == len(text.strip()):
                    endList = True

                # Else increment the list number
                elif g[3]:  # Numbered list
                    try: # digit
                        i = int(g[3])+1

                    except: # letter
                        i = chr(ord(g[3])+1)

                    autoInsertText = "{}{}{}{}".format(
                            g[1], i, g[4], g[5])

                else:  # Bullet list
                    autoInsertText = g[0]

                if text[-2:] == "  ":
                    autoInsertText = " " * len(autoInsertText)

            elif s == MS.MarkdownStateBlockquote:
                self.blockquoteRegex.indexIn(text)
                g = self.blockquoteRegex.capturedTexts()
                autoInsertText = g[0]

            elif s in [MS.MarkdownStateInGithubCodeFence,
                       MS.MarkdownStateInPandocCodeFence] and \
                 cursor.block().previous().userState() != s:
                autoInsertText = "\n" + text
                moveBack = True

            else:
                autoInsertText = self.getPriorIndentation()

        # Clear the list
        if endList:
            autoInsertText = self.getPriorIndentation()
            cursor.movePosition(QTextCursor.StartOfBlock)
            cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)
            cursor.insertText(autoInsertText)
            autoInsertText = ""

        # Finally, we insert
        cursor.insertText("\n" + autoInsertText)
        if moveBack:
            cursor.movePosition(QTextCursor.PreviousBlock)
            self.setTextCursor(cursor)

        self.ensureCursorVisible()

    def getPriorIndentation(self):
        text = self.textCursor().block().text()
        l = len(text) - len(text.lstrip())
        return text[:l]

    def getPriorMarkdownBlockItemStart(self, itemRegex):
        text = self.textCursor().block().text()
        if itemRegex.indexIn(text) >= 0:
            return text[itemRegex.matchedLength():]

        return ""

    def indentText(self):
        self._changeBlockIndentation(increase=True)

    def unindentText(self):
        self._changeBlockIndentation(increase=False)

    def _changeBlockIndentation(self, increase):
        """Indent or unindent every block touched by the cursor."""
        cursor = self.textCursor()
        original_position = cursor.position()
        original_anchor = cursor.anchor()
        selection_start = cursor.selectionStart()
        selection_end = cursor.selectionEnd()
        last_position = (
            max(selection_start, selection_end - 1)
            if cursor.hasSelection()
            else selection_start
        )

        block = self.document().findBlock(selection_start)
        last_block = self.document().findBlock(last_position)
        blocks = []
        while block.isValid():
            blocks.append(block)
            if block == last_block:
                break
            block = block.next()

        edits = []
        cursor.beginEditBlock()
        for block in reversed(blocks):
            block_cursor = QTextCursor(block)
            block_position = block.position()
            if increase:
                block_cursor.insertText("    ")
                edits.append((block_position, 0, 4))
                continue

            text = block.text()
            remove_count = 1 if text.startswith("\t") else min(
                4,
                len(text) - len(text.lstrip(" ")),
            )
            if remove_count:
                block_cursor.movePosition(
                    QTextCursor.NextCharacter,
                    QTextCursor.KeepAnchor,
                    remove_count,
                )
                block_cursor.removeSelectedText()
                edits.append((block_position, remove_count, 0))
        cursor.endEditBlock()

        def adjusted(position):
            shift = 0
            for edit_position, removed, inserted in sorted(edits):
                if removed and edit_position < position:
                    if position <= edit_position + removed:
                        return edit_position + shift
                    shift -= removed
                elif inserted and edit_position <= position:
                    shift += inserted
            return position + shift

        cursor.setPosition(adjusted(original_anchor))
        cursor.setPosition(
            adjusted(original_position),
            QTextCursor.KeepAnchor,
        )
        self.setTextCursor(cursor)

    ###########################################################################
    # TypeWriterScrolling
    ###########################################################################

    def setCurrentModelIndex(self, index):
        textEditView.setCurrentModelIndex(self, index)
        self.centerCursor()

    def cursorPositionHasChanged(self):
        self.centerCursor()
        current_position = self.textCursor().position()
        presentation_reveal = (
            self._presentationMode.reveals_active_block
        )
        focus_mode = self.settings.textEditor["focusMode"]
        if (
            self.highlighter
            and self.highlighter.document() is self.document()
            and (focus_mode or presentation_reveal)
        ):
            if self._lastCursorPosition is not None:
                previous_block = self.document().findBlock(
                    self._lastCursorPosition
                )
                self.highlighter.rehighlightBlock(previous_block)
            current_block = self.document().findBlock(current_position)
            self.highlighter.rehighlightBlock(current_block)
        self._lastCursorPosition = current_position

    def centerCursor(self, force=False):
        cursor = self.cursorRect()
        scrollbar = self.verticalScrollBar()
        viewport = self.viewport().rect()
        if (force or self.settings.textEditor["alwaysCenter"]
                or cursor.bottom() >= viewport.bottom()
                or cursor.top() <= viewport.top()):
            offset = viewport.center() - cursor.center()
            scrollbar.setValue(scrollbar.value() - offset.y())

    def scrollBarRangeChanged(self, min, max):
        """
        Adds viewport height to scrollbar max so that we can center cursor
        on screen.
        """
        if self.settings.textEditor["alwaysCenter"]:
            self.verticalScrollBar().blockSignals(True)
            self.verticalScrollBar().setMaximum(max + self.viewport().height())
            self.verticalScrollBar().blockSignals(False)

    ###########################################################################
    # FORMATTING
    ###########################################################################

    def bold(self):
        if not self._dispatchMarkupCommand("bold"):
            self.insertFormattingMarkup("**")

    def italic(self):
        if not self._dispatchMarkupCommand("italic"):
            self.insertFormattingMarkup("*")

    def underline(self):
        if not self._dispatchMarkupCommand("underline"):
            self.insertFormattingMarkup("<u>", "</u>")

    def strike(self):
        if not self._dispatchMarkupCommand("strike"):
            self.insertFormattingMarkup("~~")

    def verbatim(self):
        if not self._dispatchMarkupCommand("verbatim"):
            self.insertFormattingMarkup("`")

    def superscript(self):
        if not self._dispatchMarkupCommand("superscript"):
            self.insertFormattingMarkup("^")

    def subscript(self):
        if not self._dispatchMarkupCommand("subscript"):
            self.insertFormattingMarkup("~")

    def blockquote(self):
        if not self._dispatchMarkupCommand("blockquote"):
            self.lineFormattingMarkup("> ")

    def orderedList(self):
        if not self._dispatchMarkupCommand("ordered-list"):
            self.lineFormattingMarkup(" 1. ")

    def unorderedList(self):
        if not self._dispatchMarkupCommand("unordered-list"):
            self.lineFormattingMarkup("  - ")

    def selectWord(self, cursor):
        if cursor.selectedText():
            return
        end = cursor.selectionEnd()
        cursor.movePosition(QTextCursor.StartOfWord)
        cursor.setPosition(end, QTextCursor.KeepAnchor)
        cursor.movePosition(QTextCursor.EndOfWord, QTextCursor.KeepAnchor)

    def selectBlock(self, cursor):
        cursor.movePosition(QTextCursor.StartOfBlock)
        cursor.movePosition(QTextCursor.EndOfBlock, QTextCursor.KeepAnchor)

    def comment(self):
        if self._dispatchMarkupCommand("comment"):
            return
        cursor = self.textCursor()

        # Select beginning and end of words
        self.selectWord(cursor)

        if cursor.hasSelection():
            text = cursor.selectedText()
            cursor.insertText("<!-- " + text + " -->")
        else:
            cursor.insertText("<!--  -->")
            cursor.movePosition(QTextCursor.PreviousCharacter,
                                QTextCursor.MoveAnchor, 4)
            self.setTextCursor(cursor)

    def commentLine(self):
        if self._dispatchMarkupCommand("comment-lines"):
            return
        cursor = self.textCursor()

        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        block = self.document().findBlock(start)
        block2 = self.document().findBlock(end)

        if True:
            # Method 1
            cursor.beginEditBlock()
            while block.isValid():
                self.commentBlock(block)
                if block == block2: break
                block = block.next()
            cursor.endEditBlock()

        else:
            # Method 2
            cursor.beginEditBlock()
            cursor.setPosition(block.position())
            cursor.insertText("<!--\n")
            cursor.setPosition(block2.position() + block2.length() - 1)
            cursor.insertText("\n-->")
            cursor.endEditBlock()

    def commentBlock(self, block):
        cursor = QTextCursor(block)
        text = block.text()
        if text[:5] == "<!-- " and \
           text[-4:] == " -->":
            text2 = text[5:-4]
        else:
            text2 = "<!-- " + text + " -->"
        self.selectBlock(cursor)
        cursor.insertText(text2)

    def lineFormattingMarkup(self, markup):
        """
        Adds `markup` at the beginning of block.
        """
        cursor = self.textCursor()
        cursor.movePosition(cursor.StartOfBlock)
        cursor.insertText(markup)

    def insertFormattingMarkup(
        self,
        openingMarkup,
        closingMarkup=None,
    ):
        closingMarkup = closingMarkup or openingMarkup
        cursor = self.textCursor()

        # Select beginning and end of words
        self.selectWord(cursor)

        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        first_block = self.document().findBlock(start)
        last_block = self.document().findBlock(
            max(start, end - 1)
        )
        if first_block != last_block:
            self._wrapSelectionWithMarkup(
                cursor,
                openingMarkup,
                closingMarkup,
            )
            return

        block_text = first_block.text()
        block_position = first_block.position()
        local_start = self._pythonIndexFromUtf16Offset(
            block_text,
            start - block_position,
        )
        local_end = self._pythonIndexFromUtf16Offset(
            block_text,
            end - block_position,
        )
        edit = plan_inline_markup_toggle(
            block_text,
            local_start,
            local_end,
            openingMarkup,
            closingMarkup,
        )
        self._applyInlineMarkupEdit(
            first_block,
            block_text,
            edit,
        )

    def _applyInlineMarkupEdit(self, block, block_text, edit):
        replacement_start = (
            block.position()
            + self._utf16Length(block_text[:edit.start])
        )
        replacement_end = (
            block.position()
            + self._utf16Length(block_text[:edit.end])
        )
        updated_text = (
            block_text[:edit.start]
            + edit.replacement
            + block_text[edit.end:]
        )

        cursor = QTextCursor(self.document())
        cursor.beginEditBlock()
        cursor.setPosition(replacement_start)
        cursor.setPosition(
            replacement_end,
            QTextCursor.KeepAnchor,
        )
        cursor.insertText(edit.replacement)
        cursor.endEditBlock()

        restored = QTextCursor(self.document())
        restored.setPosition(
            block.position()
            + self._utf16Length(
                updated_text[:edit.selection_start]
            )
        )
        restored.setPosition(
            block.position()
            + self._utf16Length(
                updated_text[:edit.selection_end]
            ),
            QTextCursor.KeepAnchor,
        )
        self.setTextCursor(restored)

    def _wrapSelectionWithMarkup(
        self,
        cursor,
        openingMarkup,
        closingMarkup,
    ):
        start = cursor.selectionStart()
        end = cursor.selectionEnd()
        edit_cursor = QTextCursor(self.document())
        edit_cursor.beginEditBlock()
        edit_cursor.setPosition(end)
        edit_cursor.insertText(closingMarkup)
        edit_cursor.setPosition(start)
        edit_cursor.insertText(openingMarkup)
        edit_cursor.endEditBlock()

        restored = QTextCursor(self.document())
        restored.setPosition(start + len(openingMarkup))
        restored.setPosition(
            end + len(openingMarkup),
            QTextCursor.KeepAnchor,
        )
        self.setTextCursor(restored)

    @staticmethod
    def _utf16Length(text):
        return len(text.encode("utf-16-le")) // 2

    @classmethod
    def _pythonIndexFromUtf16Offset(cls, text, offset):
        units = 0
        for index, character in enumerate(text):
            if units == offset:
                return index
            units += cls._utf16Length(character)
            if units > offset:
                return index + 1
        return len(text)

    def clearFormat(self):
        if self._dispatchMarkupCommand("clear-format"):
            return
        cursor = self.textCursor()
        text = cursor.selectedText()
        if not text:
            self.selectBlock(cursor)
            text = cursor.selectedText()
        text = self.clearedFormat(text)
        cursor.insertText(text)

    def clearedFormat(self, text):
        replacement = self._pluginPlainText(
            text,
            remove_comments=False,
        )
        if replacement is not None:
            return replacement
        if self._markupBaseId != MARKDOWN_BASE_ID:
            return text
        return F.clearMarkdownFormatting(text)

    def clearedFormatForStats(self, text):
        replacement = self._pluginPlainText(
            text,
            remove_comments=True,
        )
        if replacement is not None:
            return replacement
        if self._markupBaseId != MARKDOWN_BASE_ID:
            return text
        return F.clearMarkdownFormatting(
            text,
            remove_comments=True,
        )

    def titleSetext(self, level):
        if self._dispatchMarkupCommand("heading-setext", level):
            return
        cursor = self.textCursor()

        cursor.beginEditBlock()
        # Is it already a Setext header?
        if cursor.block().userState() in [
                MS.MarkdownStateSetextHeading1Line2,
                MS.MarkdownStateSetextHeading2Line2]:
            cursor.movePosition(QTextCursor.PreviousBlock)

        text = cursor.block().text()

        if cursor.block().userState() in [
                MS.MarkdownStateSetextHeading1Line1,
                MS.MarkdownStateSetextHeading2Line1]:
            # Need to remove line below
            c = QTextCursor(cursor.block().next())
            self.selectBlock(c)
            c.insertText("")

        char = "=" if level == 1 else "-"
        text = re.sub(r"^#*\s*(.*)\s*#*", "\\1", text)  # Removes #
        sub = char * len(text)
        text = text + "\n" + sub

        self.selectBlock(cursor)
        cursor.insertText(text)
        cursor.endEditBlock()

    def titleATX(self, level):
        if self._dispatchMarkupCommand("heading-atx", level):
            return
        cursor = self.textCursor()
        text = cursor.block().text()

        # Are we in a Setext Header?
        if cursor.block().userState() in [
                MS.MarkdownStateSetextHeading1Line1,
                MS.MarkdownStateSetextHeading2Line1]:
            # Need to remove line below
            cursor.beginEditBlock()
            c = QTextCursor(cursor.block().next())
            self.selectBlock(c)
            c.insertText("")

            self.selectBlock(cursor)
            cursor.insertText(text)
            cursor.endEditBlock()
            return

        elif cursor.block().userState() in [
                MS.MarkdownStateSetextHeading1Line2,
                MS.MarkdownStateSetextHeading2Line2]:
            cursor.movePosition(QTextCursor.PreviousBlock)
            self.setTextCursor(cursor)
            self.titleATX(level)
            return

        m = re.match(r"^(#+)(\s*)(.+)", text)
        if m:
            pre = m.group(1)
            space = m.group(2)
            txt = m.group(3)

            if len(pre) == level:
                # Remove title
                text = txt
            else:
                text = "#" * level + space + txt

        else:
            text = "#" * level + " " + text

        self.selectBlock(cursor)
        cursor.insertText(text)

    ###########################################################################
    # CLICKABLE THINKS
    ###########################################################################

    def resizeEvent(self, event):
        textEditView.resizeEvent(self, event)
        self.scheduleInteractionRectUpdate()

    def sizeChange(self):
        if not self._autoResize:
            return
        visible_view = (
            self._presentationHost.currentWidget()
            if self._presentationHost is not None
            else self
        )
        opt = self.settings.textEditor
        doc_height = (
            visible_view.document().size().height()
            + 2 * opt["marginsTB"]
        )
        if self.heightMin <= doc_height <= self.heightMax:
            size_target = self._presentationHost or self
            size_target.setMinimumHeight(int(doc_height))

    def copy(self):
        current_view = (
            self._presentationHost.currentWidget()
            if self._presentationHost is not None
            else self
        )
        if current_view is not self:
            current_view.copy()
            return
        textEditView.copy(self)

    def scrollContentsBy(self, dx, dy):
        textEditView.scrollContentsBy(self, dx, dy)
        self.scheduleInteractionRectUpdate()

    def scheduleInteractionRectUpdate(self, *_args):
        """Coalesce document geometry changes into one rectangle rebuild."""
        if hasattr(self, "interactionRectUpdateTimer"):
            self.interactionRectUpdateTimer.start()

    def updateInteractionRects(self):
        self.getClickRects()

    def getClickRects(self):
        """
        Parses the whole texte to catch clickable things: links and images.
        Stores the result so that it can be used elsewhere.
        """
        if self._markupBaseId != MARKDOWN_BASE_ID:
            self.clickRects = []
            return
        cursor = self.textCursor()
        refs = []
        text = self.toPlainText()
        wikilink_positions = {
            link.span.start + (1 if link.embedded else 0)
            for link in self.highlighter.dslParser.parse(text).wikilinks
        }
        for rx in [
                self.imageRegex,
                self.automaticLinkRegex,
                self.inlineLinkRegex,
                self.wikilinkRegex,
            ]:
            pos = 0
            while rx.indexIn(text, pos) != -1:
                if (
                    rx is self.wikilinkRegex
                    and rx.pos() not in wikilink_positions
                ):
                    pos = rx.pos() + max(1, rx.matchedLength())
                    continue
                cursor.setPosition(rx.pos())
                r1 = self.cursorRect(cursor)
                pos = rx.pos() + rx.matchedLength()
                cursor.setPosition(pos)
                r2 = self.cursorRect(cursor)
                if r1.top() == r2.top():
                    ct = ClickThing(
                            QRect(r1.topLeft(), r2.bottomRight()),
                            rx,
                            rx.capturedTexts())
                    refs.append(ct)
                else:
                    r1.setRight(self.viewport().geometry().right())
                    refs.append(ClickThing(r1, rx, rx.capturedTexts()))
                    r2.setLeft(self.viewport().geometry().left())
                    refs.append(ClickThing(r2, rx, rx.capturedTexts()))
                    # We check for middle lines
                    cursor.setPosition(rx.pos())
                    cursor.movePosition(cursor.Down)
                    while self.cursorRect(cursor).top() != r2.top():
                        r3 = self.cursorRect(cursor)
                        r3.setLeft(self.viewport().geometry().left())
                        r3.setRight(self.viewport().geometry().right())
                        refs.append(ClickThing(r3, rx, rx.capturedTexts()))
                        if not cursor.movePosition(cursor.Down):
                            # Super-rare failure. Leaving log message for future investigation.
                            LOGGER.debug("Failed to move cursor down while calculating clickables. Aborting.")
                            break

        self.clickRects = refs

    def mouseMoveEvent(self, event):
        """
        When mouse moves, we show tooltip when appropriate.
        """
        self.beginTooltipMoveEvent()
        textEditView.mouseMoveEvent(self, event)
        self.endTooltipMoveEvent()

        onRect = [r for r in self.clickRects if r.rect.contains(event.pos())]

        if not onRect:
            qApp.restoreOverrideCursor()
            self.hideTooltip()
            return

        ct = onRect[0]
        if not qApp.overrideCursor():
            qApp.setOverrideCursor(Qt.PointingHandCursor)

        if ct.regex == self.automaticLinkRegex:
            tooltip = ct.texts[2] or ct.texts[4]

        elif ct.regex == self.imageRegex:
            tt = ("<p><b>" + ct.texts[1] + "</b></p>"
                  +"<p><img src='data:image/png;base64,{}'></p>")
            tooltip = None
            pos = event.pos() + QPoint(0, ct.rect.height())
            ImageTooltip.fromUrl(ct.texts[2], pos, self)

        elif ct.regex == self.inlineLinkRegex:
            tooltip = ct.texts[1] or ct.texts[2]

        elif ct.regex == self.wikilinkRegex:
            tooltip = ct.texts[3] or ct.texts[1]

        if tooltip:
            tooltip = self.tr("{} (CTRL+Click to open)").format(tooltip)
            self.showTooltip(self.mapToGlobal(event.pos()), tooltip)

    def mouseReleaseEvent(self, event):
        textEditView.mouseReleaseEvent(self, event)
        onRect = [r for r in self.clickRects if r.rect.contains(event.pos())]
        if onRect and event.modifiers() & Qt.ControlModifier:
            ct = onRect[0]

            if ct.regex == self.automaticLinkRegex:
                url = ct.texts[2] or ct.texts[4]
            elif ct.regex == self.imageRegex:
                url = ct.texts[2]
            elif ct.regex == self.inlineLinkRegex:
                url = ct.texts[2]

            elif ct.regex == self.wikilinkRegex:
                self.wikilinkActivated.emit(ct.texts[1].strip())
                qApp.restoreOverrideCursor()
                return

            F.openURL(url)
            qApp.restoreOverrideCursor()

    # def paintEvent(self, event):
    #     """
    #     Only useful for debugging: shows which rects are detected for
    #     clickable things.
    #     """
    #     textEditView.paintEvent(self, event)
    #
    #     # Debug: paint rects
    #     from PyQt5.QtGui import QPainter
    #     painter = QPainter(self.viewport())
    #     painter.setPen(Qt.gray)
    #     for r in self.clickRects:
    #         painter.drawRect(r.rect)

    def doTooltip(self, pos, message):
        QToolTip.showText(self.mapToGlobal(pos), message)

class ClickThing:
    """
    A simple class to remember QRect associated with clickable stuff.
    """
    def __init__(self, rect, regex, texts):
        self.rect = rect
        self.regex = regex
        self.texts = texts


class _PluginHighlightGuard:
    def __init__(self, contribution, extension, report_error):
        self.contribution = contribution
        self.extension = extension
        self.report_error = report_error
        self.failed = False

    def highlight_block(self, highlighter, text):
        if self.failed:
            return
        try:
            self.extension.highlight_block(highlighter, text)
        except Exception as error:
            self.failed = True
            self.report_error(self.contribution, error)


class _PluginBehaviorGuard:
    def __init__(self, contribution, behavior, report_error):
        self.contribution = contribution
        self.behavior = behavior
        self.report_error = report_error
        self.failed = False

    def key_press_event(self, editor, event):
        return bool(
            self._call("key_press_event", False, editor, event)
        )

    def command(self, editor, command, *arguments):
        return bool(
            self._call(
                "command",
                False,
                editor,
                command,
                *arguments,
            )
        )

    def plain_text(self, editor, text, remove_comments=False):
        return self._call(
            "plain_text",
            None,
            editor,
            text,
            remove_comments=remove_comments,
        )

    def _call(self, method, default, *arguments, **keywords):
        if self.failed:
            return default
        operation = getattr(self.behavior, method, None)
        if not callable(operation):
            return default
        try:
            return operation(*arguments, **keywords)
        except Exception as error:
            self.failed = True
            self.report_error(self.contribution, error)
            return default


class _PluginReadingRendererGuard:
    def __init__(self, contribution, report_error):
        self.contribution = contribution
        self.report_error = report_error
        self.failed = False

    def render(self, source):
        if not self.failed:
            try:
                return run_page_renderer(
                    self.contribution,
                    source,
                )
            except Exception as error:
                self.failed = True
                self.report_error(self.contribution, error)
        return RenderedDocument(
            "<pre>{}</pre>".format(html.escape(source))
        )

from PyQt5.QtNetwork import QNetworkRequest, QNetworkAccessManager, QNetworkReply
from PyQt5.QtCore import QIODevice, QUrl, QBuffer
from PyQt5.QtGui import QPixmap

class ImageTooltip:
    """
    This class handles the retrieving and caching of images in order to display these in tooltips.
    """

    cache = {}
    manager = QNetworkAccessManager()
    processing = {}

    supportedSchemes = ("", "file", "http", "https")

    def fromUrl(url, pos, editor):
        """
        Shows the image tooltip for the given url if available, or requests it for future use.
        """
        ImageTooltip.editor = editor

        if ImageTooltip.showTooltip(url, pos):
            return # the url already exists in the cache

        try:
            ImageTooltip.manager.finished.connect(ImageTooltip.finished, F.AUC)
        except:
            pass # already connected

        qurl = QUrl.fromUserInput(url)
        if (qurl == QUrl()):
            ImageTooltip.cache[url] = (False, ImageTooltip.manager.tr("The image path or URL is incomplete or malformed."))
            ImageTooltip.showTooltip(url, pos)
            return # empty QUrl means it failed completely
        elif (qurl.scheme() not in ImageTooltip.supportedSchemes):
            # QUrl.fromUserInput() can occasionally deduce an incorrect scheme,
            # which produces an error message regarding an unknown scheme. (Yay!)
            # But it also breaks all possible methods to try and associate the
            # reply with the original request in finished(), since reply.request()
            # is completely and utterly butchered for all tracking needs. :'(
            # (The QNetworkRequest, .url() and .originatingObject() can all change.)

            # Test case (Linux): ![image](C:\test_root.jpg)
            ImageTooltip.cache[url] = (False, ImageTooltip.manager.tr("The protocol \"{}\" is not supported.").format(qurl.scheme()))
            ImageTooltip.showTooltip(url, pos)
            return # no more request/reply chaos, please!
        elif (qurl in ImageTooltip.processing):
            return # one download is more than enough

        # Request the image for later processing.
        request = QNetworkRequest(qurl)
        ImageTooltip.processing[qurl] = (pos, url)
        reply = ImageTooltip.manager.get(request)

        # On Linux the finished() signal is not triggered when the url resembles
        # 'file://X:/...'. But because it completes instantly, we can manually
        # trigger the code to keep our processing dictionary neat & clean.
        if reply.error() == 302:  # QNetworkReply.ProtocolInvalidOperationError
            ImageTooltip.finished(reply)

    def finished(reply):
        """
        After retrieving an image, we add it to the cache.
        """
        cache = ImageTooltip.cache
        url_key = reply.request().url()
        pos, url = None, None

        if url_key in ImageTooltip.processing:
            # Obtain the information associated with this request.
            pos, url = ImageTooltip.processing[url_key]
            del ImageTooltip.processing[url_key]
        elif len(ImageTooltip.processing) == 0:
            # We are not processing anything. Maybe it is a spurious signal,
            # or maybe the 'reply.error() == 302' workaround in fromUrl() has
            # been fixed in Qt. Whatever the reason, we can assume this request
            # has already been handled, and needs no more work from us.
            return
        else:
            # Somehow we lost track. Log what we can to hopefully figure it out.
            LOGGER.warning("Unable to match fetched data for tooltip to original request.")
            LOGGER.warning("- Completed request: %s", url_key)
            LOGGER.warning("- Status upon finishing: %s, %s", reply.error(), reply.errorString())
            LOGGER.warning("- Currently processing: %s", ImageTooltip.processing)
            return

        # Update cache with retrieved data.
        if reply.error() != QNetworkReply.NoError:
            cache[url] = (False, reply.errorString())
        else:
            px = QPixmap()
            px.loadFromData(reply.readAll())
            px = px.scaled(800, 600, Qt.KeepAspectRatio)
            cache[url] = (True, px)

        ImageTooltip.showTooltip(url, pos)

    def showTooltip(url, pos):
        """
        Show a tooltip for the given url based on cached information.
        """
        cache = ImageTooltip.cache

        if url in cache:
            if not cache[url][0]:  # error, image was not found
                ImageTooltip.tooltipError(cache[url][1], pos)
            else:
                ImageTooltip.tooltip(cache[url][1], pos)
            return True
        return False

    def tooltipError(message, pos):
        """
        Display a tooltip with an error message at the given position.
        """
        ImageTooltip.editor.doTooltip(pos, message)

    def tooltip(image, pos):
        """
        Display a tooltip with an image at the given position.
        """
        px = image
        buffer = QBuffer()
        buffer.open(QIODevice.WriteOnly)
        px.save(buffer, "PNG", quality=100)
        image = bytes(buffer.data().toBase64()).decode()
        tt = "<p><img src='data:image/png;base64,{}'></p>".format(image)
        ImageTooltip.editor.doTooltip(pos, tt)
