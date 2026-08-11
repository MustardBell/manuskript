"""Bounded deterministic prose measurements; observations, never grades."""

import re
from collections import Counter, defaultdict
from dataclasses import dataclass

from manuskript.domain.assertion_dsl import AssertionDslExtension
from manuskript.domain.markdown_dsl import MarkdownDslParser
from manuskript.domain.rule_dsl import RuleDslExtension


WORD = re.compile(r"[^\W_]+(?:['’][^\W_]+)*", re.UNICODE)
SENTENCE = re.compile(r"[^.!?\n]+(?:[.!?]+|$)")
PARAGRAPH = re.compile(r"(?ms)(?:^|\n\s*\n)(?P<text>\S.*?)(?=\n\s*\n|$)")
QUOTED = re.compile(r"(?s)(?:\"|“)(.*?)(?:\"|”)")
PASSIVE = re.compile(
    r"(?i)\b(?:am|is|are|was|were|be|been|being)\s+"
    r"(?:\w+ly\s+)?\w+(?:ed|en)\b"
)


SPELLING_VARIANTS = (
    ("color", "colour"),
    ("center", "centre"),
    ("organize", "organise"),
    ("realize", "realise"),
    ("gray", "grey"),
    ("traveled", "travelled"),
    ("dialog", "dialogue"),
)


@dataclass(frozen=True)
class ProseDocument:
    id: str
    title: str
    text: str


@dataclass(frozen=True)
class ProseOccurrence:
    document_id: str
    start: int
    end: int
    excerpt: str


@dataclass(frozen=True)
class CountedPattern:
    pattern: str
    count: int
    occurrences: tuple[ProseOccurrence, ...] = ()


@dataclass(frozen=True)
class SimilarName:
    first: str
    second: str
    distance: int
    similarity: float


@dataclass(frozen=True)
class DocumentProseMetrics:
    document_id: str
    title: str
    word_count: int
    sentence_lengths: tuple[int, ...]
    paragraph_lengths: tuple[int, ...]
    dialogue_word_ratio: float
    punctuation: tuple[tuple[str, int], ...]


@dataclass(frozen=True)
class ProseAnalysisReport:
    documents: tuple[DocumentProseMetrics, ...]
    repeated_phrases: tuple[CountedPattern, ...]
    repeated_openings: tuple[CountedPattern, ...]
    nearby_repetitions: tuple[CountedPattern, ...]
    passive_candidates: tuple[CountedPattern, ...]
    filler_phrases: tuple[CountedPattern, ...]
    spelling_mixtures: tuple[CountedPattern, ...]
    similar_names: tuple[SimilarName, ...]


@dataclass(frozen=True)
class ProseAnalysisOptions:
    ngram_min: int = 3
    ngram_max: int = 6
    minimum_repetitions: int = 2
    opening_words: int = 3
    nearby_distance: int = 12
    fillers: tuple[str, ...] = ()
    maximum_results: int = 200

    def __post_init__(self):
        if not (2 <= self.ngram_min <= self.ngram_max <= 12):
            raise ValueError("N-gram range must be between 2 and 12 words.")
        if self.minimum_repetitions < 2:
            raise ValueError("Minimum repetitions must be at least 2.")
        if not (1 <= self.opening_words <= 8):
            raise ValueError("Sentence openings must use 1 to 8 words.")
        if not (1 <= self.nearby_distance <= 500):
            raise ValueError("Nearby distance must be 1 to 500 words.")
        if not (1 <= self.maximum_results <= 5000):
            raise ValueError("Maximum results must be 1 to 5000.")


class ProseAnalyzer:
    """Analyse explicit text with fixed algorithms and bounded output."""

    def analyze(self, documents=(), names=(), options=None):
        options = options or ProseAnalysisOptions()
        prepared = tuple(
            (document, _mask_non_prose(document.text))
            for document in documents
        )
        tokenized = tuple(
            (document, text, tuple(WORD.finditer(text)))
            for document, text in prepared
        )
        return ProseAnalysisReport(
            documents=tuple(
                _document_metrics(document, text, words)
                for document, text, words in tokenized
            ),
            repeated_phrases=_repeated_phrases(tokenized, options),
            repeated_openings=_repeated_openings(tokenized, options),
            nearby_repetitions=_nearby_repetitions(tokenized, options),
            passive_candidates=_regex_patterns(
                prepared, PASSIVE, options.maximum_results
            ),
            filler_phrases=_fillers(prepared, options),
            spelling_mixtures=_spelling_mixtures(tokenized),
            similar_names=_similar_names(
                tuple(str(name) for name in names if str(name).strip())
            ),
        )


def _mask_non_prose(source):
    spans = list(MarkdownDslParser().excluded_spans(source))
    spans.extend(node.span for node in AssertionDslExtension().parse(source).nodes)
    spans.extend(node.span for node in RuleDslExtension().parse(source).nodes)
    characters = list(source)
    for span in spans:
        for index in range(span.start, min(span.end, len(characters))):
            if characters[index] not in "\r\n":
                characters[index] = " "
    return "".join(characters)


def _document_metrics(document, text, words):
    sentences = tuple(
        len(tuple(WORD.finditer(match.group())))
        for match in SENTENCE.finditer(text)
        if WORD.search(match.group())
    )
    paragraphs = tuple(
        len(tuple(WORD.finditer(match.group("text"))))
        for match in PARAGRAPH.finditer(text)
        if WORD.search(match.group("text"))
    )
    dialogue_words = sum(
        len(tuple(WORD.finditer(match.group(1))))
        for match in QUOTED.finditer(text)
    )
    total = len(words)
    return DocumentProseMetrics(
        document.id,
        document.title,
        total,
        sentences,
        paragraphs,
        dialogue_words / total if total else 0.0,
        tuple((mark, text.count(mark)) for mark in ".,;:!?—…"),
    )


def _repeated_phrases(tokenized, options):
    found = defaultdict(list)
    spellings = {}
    for document, text, words in tokenized:
        normalized = tuple(match.group().casefold() for match in words)
        for length in range(options.ngram_min, options.ngram_max + 1):
            for start in range(0, len(words) - length + 1):
                key = normalized[start:start + length]
                spellings.setdefault(key, " ".join(
                    match.group() for match in words[start:start + length]
                ))
                found[key].append(_occurrence(
                    document.id,
                    text,
                    words[start].start(),
                    words[start + length - 1].end(),
                ))
    patterns = (
        CountedPattern(spellings[key], len(items), tuple(items))
        for key, items in found.items()
        if len(items) >= options.minimum_repetitions
    )
    return _rank(patterns, options.maximum_results)


def _repeated_openings(tokenized, options):
    found = defaultdict(list)
    for document, text, _words in tokenized:
        for sentence in SENTENCE.finditer(text):
            words = tuple(WORD.finditer(sentence.group()))
            if len(words) < options.opening_words:
                continue
            selected = words[:options.opening_words]
            key = " ".join(item.group().casefold() for item in selected)
            start = sentence.start() + selected[0].start()
            end = sentence.start() + selected[-1].end()
            found[key].append(_occurrence(document.id, text, start, end))
    return _rank((
        CountedPattern(key, len(items), tuple(items))
        for key, items in found.items()
        if len(items) >= options.minimum_repetitions
    ), options.maximum_results)


def _nearby_repetitions(tokenized, options):
    found = defaultdict(list)
    for document, text, words in tokenized:
        previous = {}
        for index, match in enumerate(words):
            key = match.group().casefold()
            prior = previous.get(key)
            if prior is not None and index - prior[0] <= options.nearby_distance:
                found[key].extend((
                    _occurrence(document.id, text, prior[1].start(), prior[1].end()),
                    _occurrence(document.id, text, match.start(), match.end()),
                ))
            previous[key] = (index, match)
    patterns = []
    for key, items in found.items():
        occurrences = tuple(_dedupe_occurrences(items))
        patterns.append(CountedPattern(key, len(occurrences), occurrences))
    return _rank(patterns, options.maximum_results)


def _regex_patterns(prepared, pattern, limit):
    found = defaultdict(list)
    for document, text in prepared:
        for match in pattern.finditer(text):
            key = match.group().casefold()
            found[key].append(_occurrence(
                document.id, text, match.start(), match.end()
            ))
    return _rank((
        CountedPattern(key, len(items), tuple(items))
        for key, items in found.items()
    ), limit)


def _fillers(prepared, options):
    patterns = []
    for filler in options.fillers:
        filler = str(filler).strip()
        if not filler:
            continue
        pattern = re.compile(r"(?i)(?<!\w){}(?!\w)".format(re.escape(filler)))
        patterns.extend(_regex_patterns(
            prepared, pattern, options.maximum_results
        ))
    return _rank(patterns, options.maximum_results)


def _spelling_mixtures(tokenized):
    counts = Counter(
        match.group().casefold()
        for _document, _text, words in tokenized for match in words
    )
    return tuple(
        CountedPattern(
            "{} / {}".format(first, second),
            counts[first] + counts[second],
        )
        for first, second in SPELLING_VARIANTS
        if counts[first] and counts[second]
    )


def _similar_names(names):
    found = []
    unique = tuple(dict.fromkeys(names))
    for index, first in enumerate(unique):
        for second in unique[index + 1:]:
            distance = _levenshtein(first.casefold(), second.casefold())
            maximum = max(len(first), len(second), 1)
            similarity = 1.0 - (distance / maximum)
            if distance <= 2 or similarity >= 0.72:
                found.append(SimilarName(
                    first, second, distance, similarity
                ))
    return tuple(sorted(
        found, key=lambda item: (-item.similarity, item.first, item.second)
    ))


def _levenshtein(first, second):
    previous = list(range(len(second) + 1))
    for first_index, first_value in enumerate(first, 1):
        current = [first_index]
        for second_index, second_value in enumerate(second, 1):
            current.append(min(
                current[-1] + 1,
                previous[second_index] + 1,
                previous[second_index - 1] + (first_value != second_value),
            ))
        previous = current
    return previous[-1]


def _occurrence(document_id, text, start, end):
    excerpt_start = max(0, start - 35)
    excerpt_end = min(len(text), end + 35)
    excerpt = re.sub(r"\s+", " ", text[excerpt_start:excerpt_end]).strip()
    return ProseOccurrence(str(document_id), start, end, excerpt)


def _rank(patterns, limit):
    return tuple(sorted(
        patterns,
        key=lambda item: (-item.count, item.pattern.casefold()),
    )[:limit])


def _dedupe_occurrences(items):
    seen = set()
    for item in items:
        key = (item.document_id, item.start, item.end)
        if key not in seen:
            seen.add(key)
            yield item
