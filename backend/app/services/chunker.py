"""
SmartPrep AI - Text Chunking Service
Handles intelligent splitting of large documents for embedding.
"""
import re
from typing import List


class TextChunker:
    """
    Splits text into overlapping chunks for embedding.
    Tries to respect sentence boundaries.
    """

    def __init__(self, chunk_size: int = 512, overlap: int = 64):
        self.chunk_size = chunk_size
        self.overlap = overlap

    def chunk(self, text: str) -> List[str]:
        """Split text into overlapping chunks, respecting sentence boundaries."""
        text = self._clean(text)
        if len(text) <= self.chunk_size:
            return [text]

        sentences = self._split_sentences(text)
        chunks = []
        current = []
        current_len = 0

        for sentence in sentences:
            s_len = len(sentence)
            if current_len + s_len > self.chunk_size and current:
                chunk = " ".join(current).strip()
                if chunk:
                    chunks.append(chunk)
                # Keep overlap sentences
                overlap_text = " ".join(current)
                overlap_start = max(0, len(overlap_text) - self.overlap)
                carry = overlap_text[overlap_start:].strip()
                current = [carry] if carry else []
                current_len = len(carry)

            current.append(sentence)
            current_len += s_len + 1

        # Last chunk
        if current:
            chunk = " ".join(current).strip()
            if chunk:
                chunks.append(chunk)

        return [c for c in chunks if len(c) > 30]  # Filter trivially short chunks

    def _clean(self, text: str) -> str:
        """Normalize whitespace and remove noise."""
        text = re.sub(r"\n{3,}", "\n\n", text)
        text = re.sub(r"[ \t]{2,}", " ", text)
        text = text.strip()
        return text

    def _split_sentences(self, text: str) -> List[str]:
        """Split on sentence boundaries."""
        sentences = re.split(r"(?<=[.!?])\s+|\n\n", text)
        return [s.strip() for s in sentences if s.strip()]
