"""Workspace-local progress for one writing session."""

from dataclasses import dataclass


@dataclass
class WritingSessionProgress:
    """The word-count baseline from which this workspace measures progress."""

    start_word_count: int = 0

    def reset(self, word_count):
        self.start_word_count = int(word_count)

    def words_written(self, total_word_count):
        return int(total_word_count) - self.start_word_count
