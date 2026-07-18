from __future__ import annotations

import os
import re
from urllib.parse import quote, urlparse

import httpx

from app.models import Paper

_MAX_OPENALEX_BYTES = 2_000_000
_EMBEDDABLE_PDF_HOSTS = {
    "arxiv.org",
    "export.arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "proceedings.mlr.press",
    "openaccess.thecvf.com",
    "semanticscholar.org",
    "pdfs.semanticscholar.org",
}
_BYTE_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def direct_pdf_urls_enabled() -> bool:
    return os.environ.get("CHAT_PDF_DIRECT_URLS", "true").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def public_pdf_viewer_url(paper_id: str, resolved: str | None) -> str | None:
    if not resolved:
        return None
    if direct_pdf_urls_enabled():
        return resolved
    return f"/papers/{quote(paper_id, safe='')}/pdf"


def parse_byte_range(value: str | None, total: int) -> tuple[int, int] | None:
    """Parse one HTTP byte range, returning an inclusive start/end pair."""
    if not value:
        return None
    match = _BYTE_RANGE_RE.fullmatch(value.strip())
    if not match or total <= 0:
        raise ValueError("range_not_satisfiable")
    start_text, end_text = match.groups()
    if not start_text and not end_text:
        raise ValueError("range_not_satisfiable")
    if not start_text:
        suffix = int(end_text)
        if suffix <= 0:
            raise ValueError("range_not_satisfiable")
        return max(0, total - suffix), total - 1
    start = int(start_text)
    if start >= total:
        raise ValueError("range_not_satisfiable")
    end = total - 1 if not end_text else min(int(end_text), total - 1)
    if end < start:
        raise ValueError("range_not_satisfiable")
    return start, end


def _embeddable_pdf_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    host = (parsed.hostname or "").lower().rstrip(".")
    trusted = any(
        host == allowed or host.endswith(f".{allowed}")
        for allowed in _EMBEDDABLE_PDF_HOSTS
    )
    return value if parsed.scheme == "https" and trusted else None


async def resolve_paper_viewer_url(
    paper: Paper,
    *,
    client: httpx.AsyncClient | None = None,
) -> str | None:
    """Prefer a browser-embeddable PDF while retaining canonical metadata."""
    direct = _embeddable_pdf_url(paper.pdf_url)
    if direct:
        return direct

    paper_id = str(paper.id or "")
    if not paper_id.startswith("openalex:"):
        return None

    work_id = paper_id.split(":", 1)[1]
    owns_client = client is None
    if client is None:
        client = httpx.AsyncClient(timeout=10, follow_redirects=False)
    try:
        response = await client.get(
            f"https://api.openalex.org/works/{quote(work_id, safe='')}"
        )
    except httpx.HTTPError:
        return None
    finally:
        if owns_client:
            await client.aclose()

    if response.status_code != 200 or len(response.content) > _MAX_OPENALEX_BYTES:
        return None
    try:
        locations = response.json().get("locations", [])
    except ValueError:
        return None
    for location in locations:
        resolved = _embeddable_pdf_url(location.get("pdf_url"))
        if resolved:
            return resolved
    return None
