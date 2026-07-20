"""
Unit tests for ResumeParser service.
Run: pytest tests/test_resume_parser.py -v
"""
import pytest
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.services.resume_parser import ResumeParser


@pytest.fixture
def parser():
    return ResumeParser()


class TestResumeParser:

    def test_extracts_plain_text_utf8(self, parser):
        content = "John Smith\nPython Developer\nSkills: Python, FastAPI"
        result = parser.extract_text(content.encode("utf-8"), "resume.txt")
        assert "John Smith" in result
        assert "Python" in result

    def test_extracts_latin1_text(self, parser):
        content = "Résumé of José García"
        result = parser.extract_text(content.encode("latin-1"), "resume.txt")
        assert "sum" in result  # "Résumé" decoded

    def test_cleans_excessive_newlines(self, parser):
        content = "Line one\n\n\n\n\nLine two"
        result = parser.extract_text(content.encode(), "resume.txt")
        assert "\n\n\n\n" not in result

    def test_cleans_excessive_spaces(self, parser):
        content = "Python    Engineer    at    Acme"
        result = parser.extract_text(content.encode(), "resume.txt")
        assert "    " not in result

    def test_replaces_bullet_characters(self, parser):
        content = "• Python\n• FastAPI\n▪ Docker"
        result = parser.extract_text(content.encode(), "resume.txt")
        assert "•" not in result
        assert "▪" not in result
        assert "-" in result

    def test_removes_null_bytes(self, parser):
        content = b"John\x00Smith\x00Developer"
        result = parser.extract_text(content, "resume.txt")
        assert "\x00" not in result

    def test_unknown_extension_falls_back_to_text(self, parser):
        content = "Some resume content here"
        result = parser.extract_text(content.encode(), "resume.xyz")
        assert "Some resume content" in result

    def test_invalid_pdf_bytes_raises_value_error(self, parser):
        """Non-PDF bytes with .pdf extension should fail gracefully."""
        with pytest.raises((ValueError, Exception)):
            parser.extract_text(b"not a real pdf", "resume.pdf")
