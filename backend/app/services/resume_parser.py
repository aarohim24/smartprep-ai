"""
SmartPrep AI - Resume Parsing Service
Handles PDF and plain text resume extraction.
"""
import io
import re
from typing import Tuple

import pdfplumber
from app.utils.logger import setup_logger

logger = setup_logger(__name__)


class ResumeParser:
    """Extracts clean text from resume files (PDF or plain text)."""

    MAX_FILE_SIZE_MB = 10

    def extract_text(self, file_bytes: bytes, filename: str) -> str:
        """Extract text from uploaded resume file."""
        ext = filename.lower().rsplit(".", 1)[-1] if "." in filename else "txt"

        if ext == "pdf":
            return self._extract_pdf(file_bytes)
        elif ext in ("txt", "text", "md"):
            return self._extract_text(file_bytes)
        else:
            # Try PDF first, fall back to text
            try:
                return self._extract_pdf(file_bytes)
            except Exception:
                return self._extract_text(file_bytes)

    def _extract_pdf(self, file_bytes: bytes) -> str:
        """Extract text from PDF using pdfplumber."""
        text_parts = []
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            logger.info(f"PDF has {len(pdf.pages)} pages")
            for page_num, page in enumerate(pdf.pages):
                page_text = page.extract_text(x_tolerance=3, y_tolerance=3)
                if page_text:
                    text_parts.append(page_text)

        full_text = "\n\n".join(text_parts)
        cleaned = self._clean_text(full_text)

        if len(cleaned) < 100:
            raise ValueError("Could not extract meaningful text from PDF")

        logger.info(f"Extracted {len(cleaned)} chars from PDF")
        return cleaned

    def _extract_text(self, file_bytes: bytes) -> str:
        """Extract from plain text file."""
        try:
            text = file_bytes.decode("utf-8")
        except UnicodeDecodeError:
            text = file_bytes.decode("latin-1", errors="replace")
        return self._clean_text(text)

    def _clean_text(self, text: str) -> str:
        """Clean extracted text."""
        # Remove excessive whitespace
        text = re.sub(r"\n{4,}", "\n\n\n", text)
        text = re.sub(r"[ \t]{3,}", " ", text)
        # Remove null bytes
        text = text.replace("\x00", "")
        # Normalize dashes/bullets
        text = re.sub(r"[•·▪▸➤►▷]", "-", text)
        return text.strip()


# Singleton instance
resume_parser = ResumeParser()
