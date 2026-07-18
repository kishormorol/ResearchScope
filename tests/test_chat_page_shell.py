from pathlib import Path


SITE = Path(__file__).resolve().parents[1] / "site"


def _fragment(page: str, tag: str) -> str:
    html = (SITE / page).read_text(encoding="utf-8")
    start = html.index(f"<{tag}")
    end = html.index(f"</{tag}>", start) + len(f"</{tag}>")
    return html[start:end]


def test_chat_pages_reuse_the_papers_header_and_footer():
    papers_nav = _fragment("papers.html", "nav")
    papers_footer = _fragment("papers.html", "footer")

    for page in ("chat-arxiv.html", "chat-paper.html"):
        assert _fragment(page, "nav") == papers_nav
        assert _fragment(page, "footer") == papers_footer


def test_chat_pages_load_the_shared_theme_bootstrap():
    for page in ("chat-arxiv.html", "chat-paper.html"):
        html = (SITE / page).read_text(encoding="utf-8")
        assert "assets/js/theme-bootstrap.js?v=ui-integrity-18" in html
