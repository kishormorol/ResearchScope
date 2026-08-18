"""ACL Anthology PDF URLs must not carry the landing page's trailing slash."""
from __future__ import annotations

from src.connectors.acl_connector import ACLAnthologyConnector


def _connector() -> ACLAnthologyConnector:
    return ACLAnthologyConnector()


class TestBibRecordPdfUrl:
    def test_trailing_slash_landing_url_yields_valid_pdf_url(self):
        # The Anthology serves "<key>/" as the landing page; naively appending
        # ".pdf" gave "<key>/.pdf", which 404s for every ACL paper.
        paper = _connector()._export_record_to_paper(
            "2026.acl-long.125",
            {"url": "https://aclanthology.org/2026.acl-long.125/",
             "title": "A Title", "author": "Ada Lovelace",
             "year": "2026", "abstract": "x"},
            "acl",
        )
        assert paper.pdf_url == "https://aclanthology.org/2026.acl-long.125.pdf"
        assert "/.pdf" not in paper.pdf_url

    def test_explicit_pdf_field_wins(self):
        paper = _connector()._export_record_to_paper(
            "2026.acl-long.125",
            {"url": "https://aclanthology.org/2026.acl-long.125/",
             "pdf": "https://example.org/custom.pdf",
             "title": "A Title", "author": "Ada Lovelace", "year": "2026"},
            "acl",
        )
        assert paper.pdf_url == "https://example.org/custom.pdf"


class TestSearchItemPdfUrl:
    def test_no_double_extension(self):
        paper = _connector()._search_item_to_paper({
            "acl_id": "2026.emnlp-main.7", "title": "T",
            "authors": ["A B"], "year": "2026", "venue": "EMNLP",
        })
        assert paper.pdf_url == "https://aclanthology.org/2026.emnlp-main.7.pdf"
        assert "/.pdf" not in paper.pdf_url

    def test_missing_id_yields_no_pdf_url(self):
        paper = _connector()._search_item_to_paper({
            "title": "T", "authors": ["A B"], "year": "2026",
        })
        assert paper.pdf_url == ""
