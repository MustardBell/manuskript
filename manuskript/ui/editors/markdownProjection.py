from bisect import bisect_left

from PyQt5.QtGui import (
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
)


class MarkdownProjectionMap:
    """Translate positions in a rendered document back to Markdown source."""

    def __init__(self, positions):
        self._positions = positions

    @classmethod
    def from_document(cls, document, source_text):
        positions = []
        source_position = 0
        for document_position in range(document.characterCount()):
            character = document.characterAt(document_position)
            if character in ("\u2028", "\u2029"):
                character = "\n"
            if character in ("\ufffc", "\x00"):
                positions.append(source_position)
                continue

            match = source_text.find(character, source_position)
            if match < 0:
                positions.append(source_position)
                continue
            positions.append(match)
            source_position = match + 1
        return cls(positions)

    def source_position_at(self, position):
        if not self._positions:
            return None
        position = min(max(0, position), len(self._positions) - 1)
        return self._positions[position]

    def projection_position_at(self, source_position):
        """Return the rendered position nearest to a source position."""
        if not self._positions:
            return None
        position = bisect_left(self._positions, source_position)
        return min(position, len(self._positions) - 1)

    def rendered_range_for(self, document, source_block):
        source_start = source_block.position()
        source_end = source_start + len(source_block.text())
        positions = [
            position
            for position, source_position in enumerate(self._positions)
            if source_start <= source_position < source_end
        ]
        if positions:
            return positions[0], positions[-1] + 1

        insertion_position = next(
            (
                position
                for position, source_position
                in enumerate(self._positions)
                if source_position >= source_start
            ),
            max(0, document.characterCount() - 1),
        )
        return insertion_position, insertion_position


class MarkdownProjectionRenderer:
    """Build a rendered document and expose one source block inside it."""

    def __init__(self, source_editor):
        self._sourceEditor = source_editor

    def render(self, document, source_block):
        source_document = self._sourceEditor.document()
        source_text = self._sourceEditor.toPlainText()
        document.clear()
        document.setDefaultFont(self._sourceEditor.font())
        document.setDocumentMargin(source_document.documentMargin())
        document.setMarkdown(
            source_text,
            QTextDocument.MarkdownDialectGitHub,
        )

        rendered_map = MarkdownProjectionMap.from_document(
            document,
            source_text,
        )
        rendered_range = rendered_map.rendered_range_for(
            document,
            source_block,
        )
        active_range = self._expose_source_block(
            document,
            rendered_map,
            source_block,
            rendered_range,
        )
        position_map = MarkdownProjectionMap.from_document(
            document,
            source_text,
        )
        return active_range, position_map

    def replace_active_source(
        self,
        document,
        active_range,
        source_block,
    ):
        range_start, range_end = active_range
        cursor = QTextCursor(document)
        cursor.setPosition(range_start)
        cursor.setPosition(range_end, QTextCursor.KeepAnchor)
        cursor.insertText(
            source_block.text(),
            self._source_char_format(),
        )
        return range_start, range_start + len(source_block.text())

    def _expose_source_block(
        self,
        document,
        rendered_map,
        source_block,
        rendered_range,
    ):
        range_start, range_end = rendered_range
        cursor = QTextCursor(document)
        cursor.setPosition(range_start)
        cursor.setPosition(range_end, QTextCursor.KeepAnchor)

        rendered_block = document.findBlock(range_start)
        rendered_block_start = rendered_block.position()
        rendered_block_end = (
            rendered_block.position() + len(rendered_block.text())
        )
        source_start = source_block.position()
        source_end = source_start + len(source_block.text())
        block_mapping = [
            rendered_map.source_position_at(position)
            for position in range(
                rendered_block_start,
                rendered_block_end,
            )
        ]
        has_other_source_lines = any(
            source_position < source_start
            or source_position >= source_end
            for source_position in block_mapping
        )

        char_format = self._source_char_format()
        block_format = self._source_block_format()

        if not source_block.text():
            cursor.clearSelection()
            cursor.insertBlock(block_format, char_format)
            return cursor.block().position(), cursor.block().position()

        if has_other_source_lines:
            cursor.insertText(
                "\n{}\n".format(source_block.text()),
                char_format,
            )
            active_block = document.findBlock(range_start + 1)
            QTextCursor(active_block).setBlockFormat(block_format)
            return (
                active_block.position(),
                active_block.position() + len(active_block.text()),
            )

        cursor.insertText(source_block.text(), char_format)
        active_block = document.findBlock(range_start)
        QTextCursor(active_block).setBlockFormat(block_format)
        return range_start, range_start + len(source_block.text())

    def _source_char_format(self):
        char_format = QTextCharFormat(
            self._sourceEditor._defaultCharFormat
        )
        char_format.setFont(self._sourceEditor.font())
        return char_format

    def _source_block_format(self):
        block_format = QTextBlockFormat(
            self._sourceEditor._defaultBlockFormat
        )
        block_format.setObjectIndex(-1)
        return block_format
