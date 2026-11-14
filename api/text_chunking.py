import re
from dataclasses import dataclass
from typing import Protocol

from markdown_it_rs_py import MarkdownIt

__all__ = ["ChunkingConfig", "TextNormalizer", "TextChunker", "chunk_text"]


_SENTENCE_BOUNDARY_CHARS = ".!?。！？"
_SENTENCE_CLOSING_CHARS = "\"'”’）)]}」』】》〉〕］｝〗〙〛"
_SENTENCE_END_RE = re.compile(
    rf"[^{re.escape(_SENTENCE_BOUNDARY_CHARS)}]+"
    rf"[{re.escape(_SENTENCE_BOUNDARY_CHARS)}]+"
    rf"[{re.escape(_SENTENCE_CLOSING_CHARS)}]*"
)


# TODO: token base chunker
class Chunker(Protocol):
    def chunk(self, text: str) -> list[str]: ...


@dataclass(frozen=True)
class ChunkingConfig:
    size: int = 500
    overlap: int = 50

    def __post_init__(self):
        if self.size <= 0:
            raise ValueError("size must be positive")
        if self.overlap < 0:
            raise ValueError("overlap must be non-negative")
        if self.size <= self.overlap:
            raise ValueError("overlap must smaller than chunk size")


class TextNormalizer:
    _markdown = MarkdownIt()

    @classmethod
    def normalize(cls, text: str) -> str:
        text = cls._markdown.strip_markdown(text.lstrip("\r\n"))
        lines = (re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines())
        return "\n".join(line for line in lines if line)


@dataclass(frozen=True)
class _TextUnit:
    text: str
    separator_before: str = " "


class TextChunker(Chunker):
    SENTENCE_END_RE = _SENTENCE_END_RE

    def __init__(
        self, config: ChunkingConfig = None, normalizer: TextNormalizer = None
    ):
        self.config = config or ChunkingConfig()
        self.normalizer = normalizer or TextNormalizer()

    def chunk(self, text: str) -> list[str]:
        """core method. chunk text to makesure it less than a fixed length"""
        text = self.normalizer.normalize(text)
        if not text:
            return []
        if len(text) <= self.config.size:
            return [text]

        units = self._to_atomic_units(text)
        return self._merge_units(units)

    def _to_atomic_units(self, text: str) -> list[_TextUnit]:
        """split text to text units. makesure each unit is shorter than chunk_size"""

        units: list[_TextUnit] = []
        for paragraph in text.splitlines():
            paragraph = paragraph.strip()
            # empty paragraph
            if not paragraph:
                continue

            # add the paragraph if possible
            if len(paragraph) <= self.config.size:
                paragraph_units = self._split_sentences(paragraph)
            else:
                paragraph_units = []
                for sentence in self._split_sentences(paragraph):
                    paragraph_units.extend(self._split_long_text(sentence))

            for index, unit in enumerate(paragraph_units):
                separator = "\n" if units and index == 0 else " "
                units.append(_TextUnit(unit, separator))

        return units

    def _split_sentences(self, text: str) -> list[str]:
        """a long text -> a sentences list"""

        last_end = 0
        sentences: list[str] = []
        # find all sentence ending
        for match in self.SENTENCE_END_RE.finditer(text):
            sentence = match.group().strip()
            if sentence:
                sentences.append(sentence)
            last_end = match.end()

        # process tailing text
        tail = text[last_end:].strip()
        if tail:
            sentences.append(tail)

        if sentences:
            return sentences
        # can't split. hard cut it
        return self._split_long_text(text)

    def _split_long_text(self, text: str) -> list[str]:
        """makesure text is shorter than config.size"""

        if len(text) <= self.config.size:
            return [text]
        return [
            text[start : start + self.config.size].strip()
            for start in range(0, len(text), self.config.size)
            if text[start : start + self.config.size].strip()
        ]

    def _merge_units(self, units: list[_TextUnit]) -> list[str]:
        """units -> text"""

        chunks: list[str] = []  # result
        current: list[_TextUnit] = []  # current text
        for unit in units:
            tmp = self._join_units([*current, unit])
            if current and len(tmp) > self.config.size:
                # if looger then configured append it to result
                chunks.append(self._join_units(current))
                current = self._overlap_units(current)
                tmp = self._join_units([*current, unit])
                if len(tmp) > self.config.size:
                    current = [unit]
                else:
                    current.append(unit)
            else:
                current.append(unit)

        if current:
            chunks.append(self._join_units(current))

        return chunks

    def _overlap_units(self, units: list[_TextUnit]) -> list[_TextUnit]:
        """overlap"""

        selected: list[_TextUnit] = []
        for unit in reversed(units):
            # makesure it shorter than config.overlap
            tmp = self._join_units([unit, *selected])
            if len(tmp) > self.config.overlap:
                break
            selected.insert(0, unit)

        return selected

    @staticmethod
    def _join_units(units: list[_TextUnit]) -> str:
        parts: list[str] = []
        for unit in units:
            text = unit.text.strip()
            if not text:
                continue
            if parts:
                parts.append(unit.separator_before)
            parts.append(text)
        return "".join(parts).strip()


# helper method
def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    config = ChunkingConfig(size=chunk_size, overlap=overlap)
    chunker = TextChunker(config)
    return chunker.chunk(text)
