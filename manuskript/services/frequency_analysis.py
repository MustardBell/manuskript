import re
from collections import Counter


def _walk_text(item):
    yield item.text()
    for child in item.children():
        yield from _walk_text(child)


def word_frequencies(root, minimum_length=1, excluded=()):
    excluded = {word.strip().lower() for word in excluded}
    words = []
    for text in _walk_text(root):
        words.extend(re.findall(r"[\w']+", text))

    normalized = (
        word.lower()
        for word in words
        if len(word) >= minimum_length
        and word.lower() not in excluded
    )
    return Counter(normalized)


def phrase_frequencies(root, minimum_words, maximum_words):
    phrases = []
    for text in _walk_text(root):
        words = re.findall(r"[\w']+", text)
        for length in range(minimum_words, maximum_words + 1):
            for offset in range(len(words) - length + 1):
                phrases.append(
                    tuple(words[offset:offset + length])
                )
    return Counter(phrases)
