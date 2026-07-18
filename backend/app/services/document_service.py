from __future__ import annotations

import asyncio
import base64
import hashlib
import ipaddress
import logging
import os
import re
import socket
import time
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urljoin, urlparse

import fitz
import httpx
import tiktoken
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.database import get_session_factory
from app.models import Paper, PaperChunk, PaperDocument
from app.services.provider_service import (
    ProviderConfigurationError,
    ProviderRequestError,
    create_embeddings,
    embeddings_enabled,
    get_embedding_config,
)
from app.services.quota_service import (
    GlobalCostLimitExceeded,
    QuotaConfigurationError,
    reserve_global_provider_budget,
)

EXTRACTOR_VERSION = "pymupdf-hybrid-v2"
_PREPARE_SEMAPHORE = asyncio.Semaphore(2)
_STALE_AFTER = timedelta(minutes=15)
log = logging.getLogger(__name__)

_PDF_CACHE: OrderedDict[str, tuple[float, bytes]] = OrderedDict()
_PDF_INFLIGHT: dict[str, asyncio.Task[bytes]] = {}
_PDF_CACHE_LOCK = asyncio.Lock()

_UNSAFE_TEXT_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]")

_DEFAULT_HOSTS = {
    "arxiv.org",
    "export.arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "proceedings.mlr.press",
    "openaccess.thecvf.com",
    "semanticscholar.org",
    "pdfs.semanticscholar.org",
    "nature.com",
    "pmc.ncbi.nlm.nih.gov",
    "europepmc.org",
}


@dataclass(frozen=True)
class ExtractedChunk:
    chunk_index: int
    page_start: int
    page_end: int
    content: str
    section: str | None = None
    parent_chunk_index: int | None = None
    content_type: str = "paragraph"
    token_count: int = 0
    bounding_box: dict[str, float] | None = None


@dataclass(frozen=True)
class PageBlock:
    page_number: int
    content: str
    content_type: str
    bounding_box: dict[str, float]


class DocumentPreparationError(RuntimeError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def sanitize_extracted_text(value: str) -> str:
    """Remove control characters that PostgreSQL TEXT cannot safely store."""
    return _UNSAFE_TEXT_RE.sub("", value)


def _allowed_hosts() -> set[str]:
    extra = {
        item.strip().lower()
        for item in os.environ.get("CHAT_PDF_ALLOWED_HOSTS", "").split(",")
        if item.strip()
    }
    return _DEFAULT_HOSTS | extra


def document_is_current(document: PaperDocument) -> bool:
    if document.extractor_version != EXTRACTOR_VERSION:
        return False
    if not embeddings_enabled():
        return True
    expected_model = (
        os.environ.get("OPENAI_EMBEDDING_MODEL", "text-embedding-3-large").strip()
        or "text-embedding-3-large"
    )
    try:
        expected_dimensions = int(os.environ.get("OPENAI_EMBEDDING_DIMENSIONS", "256"))
    except ValueError:
        return False
    return (
        document.embedding_model == expected_model
        and document.embedding_dimensions == expected_dimensions
    )


def _host_allowed(host: str, allowed: set[str] | None = None) -> bool:
    host = host.lower().rstrip(".")
    return any(
        host == item or host.endswith(f".{item}")
        for item in (allowed or _allowed_hosts())
    )


def resolve_pdf_url(paper: Paper) -> str | None:
    if paper.pdf_url:
        return paper.pdf_url.strip()

    pid = str(paper.id or "")
    purl = str(paper.paper_url or "")
    source = str(paper.source or "").lower()

    if source == "arxiv" or pid.startswith("arxiv:"):
        arxiv_id = pid.split(":", 1)[-1].split("v", 1)[0]
        return f"https://arxiv.org/pdf/{arxiv_id}"
    if source == "openreview" or pid.startswith("openreview:"):
        forum = pid.split(":", 1)[-1] if ":" in pid else ""
        if not forum and purl:
            forum = parse_qs(urlparse(purl).query).get("id", [""])[0]
        return f"https://openreview.net/pdf?id={forum}" if forum else None
    if source == "acl_anthology" or pid.startswith("acl:"):
        acl_id = (
            pid.split(":", 1)[-1] if ":" in pid else purl.rstrip("/").rsplit("/", 1)[-1]
        )
        return f"https://aclanthology.org/{acl_id}.pdf" if acl_id else None
    if source == "cvf" and purl.endswith(".html") and "/html/" in purl:
        return purl.replace("/html/", "/papers/")[:-5] + ".pdf"
    return None


def safe_pdf_url(paper: Paper) -> str | None:
    url = resolve_pdf_url(paper)
    if not url:
        return None
    parsed = urlparse(url)
    if parsed.scheme != "https" or not _host_allowed(parsed.hostname or ""):
        return None
    return url


async def _validate_public_host(host: str) -> None:
    if not host or not _host_allowed(host):
        raise DocumentPreparationError("pdf_host_not_allowed")
    try:
        infos = await asyncio.to_thread(
            socket.getaddrinfo, host, 443, type=socket.SOCK_STREAM
        )
    except OSError as exc:
        raise DocumentPreparationError("pdf_host_unreachable") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if not address.is_global:
            raise DocumentPreparationError("pdf_host_not_public")


def clear_pdf_cache() -> None:
    """Clear process-local PDF state. Primarily useful for deterministic tests."""
    _PDF_CACHE.clear()
    _PDF_INFLIGHT.clear()


def _pdf_cache_setting(name: str, default: int) -> int:
    try:
        value = int(os.environ.get(name, str(default)).strip())
    except ValueError as exc:
        raise DocumentPreparationError("pdf_configuration_invalid") from exc
    if value < 0:
        raise DocumentPreparationError("pdf_configuration_invalid")
    return value


async def download_pdf(url: str) -> bytes:
    ttl = _pdf_cache_setting("CHAT_PDF_CACHE_TTL_SECONDS", 3600)
    max_entries = _pdf_cache_setting("CHAT_PDF_CACHE_MAX_ENTRIES", 4)
    now = time.monotonic()
    owner = False
    async with _PDF_CACHE_LOCK:
        cached = _PDF_CACHE.get(url)
        if cached and cached[0] > now:
            _PDF_CACHE.move_to_end(url)
            return cached[1]
        if cached:
            _PDF_CACHE.pop(url, None)
        task = _PDF_INFLIGHT.get(url)
        if task is None:
            task = asyncio.create_task(_download_pdf_uncached(url))
            _PDF_INFLIGHT[url] = task
            owner = True
    try:
        result = await asyncio.shield(task)
    except BaseException:
        if owner:
            async with _PDF_CACHE_LOCK:
                _PDF_INFLIGHT.pop(url, None)
        raise
    if owner:
        async with _PDF_CACHE_LOCK:
            _PDF_INFLIGHT.pop(url, None)
            if ttl and max_entries:
                _PDF_CACHE[url] = (time.monotonic() + ttl, result)
                _PDF_CACHE.move_to_end(url)
                while len(_PDF_CACHE) > max_entries:
                    _PDF_CACHE.popitem(last=False)
    return result


async def _download_pdf_uncached(url: str) -> bytes:
    max_bytes = int(float(os.environ.get("CHAT_MAX_PDF_MB", "15")) * 1024 * 1024)
    timeout = httpx.Timeout(
        float(os.environ.get("CHAT_PDF_TIMEOUT_SECONDS", "60")), connect=10
    )
    current = url

    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False) as client:
        for _ in range(4):
            parsed = urlparse(current)
            if parsed.scheme != "https":
                raise DocumentPreparationError("pdf_https_required")
            await _validate_public_host(parsed.hostname or "")

            async with client.stream(
                "GET", current, headers={"User-Agent": "ResearchScope/1.0"}
            ) as response:
                if response.status_code in {301, 302, 303, 307, 308}:
                    location = response.headers.get("location")
                    if not location:
                        raise DocumentPreparationError("pdf_redirect_invalid")
                    current = urljoin(current, location)
                    continue
                if response.status_code != 200:
                    raise DocumentPreparationError("pdf_download_failed")
                declared = int(response.headers.get("content-length") or 0)
                if declared > max_bytes:
                    raise DocumentPreparationError("pdf_too_large")
                data = bytearray()
                async for part in response.aiter_bytes():
                    data.extend(part)
                    if len(data) > max_bytes:
                        raise DocumentPreparationError("pdf_too_large")
                result = bytes(data)
                if not result.startswith(b"%PDF-"):
                    raise DocumentPreparationError("pdf_invalid")
                return result
    raise DocumentPreparationError("pdf_redirect_limit")


_HEADING_RE = re.compile(
    r"^(?:\d+(?:\.\d+)*\s+)?(?:abstract|introduction|background|related work|"
    r"method(?:ology)?|approach|model|experiments?|evaluation|results?|discussion|"
    r"limitations?|conclusion|references|appendix)\b",
    re.IGNORECASE,
)
_CAPTION_RE = re.compile(r"^(fig(?:ure)?\.?|table)\s*\d+", re.IGNORECASE)


def count_tokens(text: str) -> int:
    return len(tiktoken.get_encoding("cl100k_base").encode(text))


def _split_by_tokens(text: str, target: int, overlap: int) -> list[str]:
    encoding = tiktoken.get_encoding("cl100k_base")
    tokens = encoding.encode(text)
    if not tokens:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(tokens):
        end = min(len(tokens), start + target)
        decoded = encoding.decode(tokens[start:end]).strip()
        if decoded:
            chunks.append(decoded)
        if end >= len(tokens):
            break
        start = max(start + 1, end - overlap)
    return chunks


def _content_type(text: str) -> str:
    normalized = " ".join(text.split())
    if _HEADING_RE.match(normalized) and len(normalized) <= 160:
        return "section_heading"
    match = _CAPTION_RE.match(normalized)
    if match:
        return (
            "table_caption" if match.group(1).lower() == "table" else "figure_caption"
        )
    return "paragraph"


def _extract_page_blocks(document: fitz.Document) -> list[list[PageBlock]]:
    pages: list[list[PageBlock]] = []
    for page_number, page in enumerate(document, start=1):
        blocks: list[PageBlock] = []
        for raw in page.get_text("blocks", sort=True):
            x0, y0, x1, y1, raw_text = raw[:5]
            raw_text = sanitize_extracted_text(str(raw_text))
            text = "\n".join(
                " ".join(line.split()) for line in raw_text.splitlines() if line.strip()
            ).strip()
            if not text:
                continue
            blocks.append(
                PageBlock(
                    page_number=page_number,
                    content=text,
                    content_type=_content_type(text),
                    bounding_box={
                        "x0": round(float(x0), 2),
                        "y0": round(float(y0), 2),
                        "x1": round(float(x1), 2),
                        "y1": round(float(y1), 2),
                    },
                )
            )
        pages.append(blocks)
    return pages


def _merged_box(blocks: list[PageBlock]) -> dict[str, float] | None:
    if not blocks:
        return None
    return {
        "x0": min(block.bounding_box["x0"] for block in blocks),
        "y0": min(block.bounding_box["y0"] for block in blocks),
        "x1": max(block.bounding_box["x1"] for block in blocks),
        "y1": max(block.bounding_box["y1"] for block in blocks),
    }


def chunk_structured_pages(
    pages: list[list[PageBlock]],
    *,
    child_tokens: int = 600,
    parent_tokens: int = 1500,
    overlap_tokens: int = 100,
) -> list[ExtractedChunk]:
    chunks: list[ExtractedChunk] = []
    index = 0
    current_section: str | None = None

    for blocks in pages:
        groups: list[tuple[str | None, list[PageBlock]]] = []
        active: list[PageBlock] = []
        active_section = current_section
        for block in blocks:
            if block.content_type == "section_heading":
                if active:
                    groups.append((active_section, active))
                    active = []
                current_section = " ".join(block.content.split())[:160]
                active_section = current_section
            active.append(block)
        if active:
            groups.append((active_section, active))

        for section, group in groups:
            text = "\n\n".join(block.content for block in group).strip()
            if not text:
                continue
            page_number = group[0].page_number
            box = _merged_box(group)
            has_table = any(block.content_type == "table_caption" for block in group)
            has_figure = any(block.content_type == "figure_caption" for block in group)
            child_type = (
                "table" if has_table else "figure" if has_figure else "paragraph"
            )
            for parent_text in _split_by_tokens(text, parent_tokens, 0):
                parent_index = index
                chunks.append(
                    ExtractedChunk(
                        chunk_index=index,
                        page_start=page_number,
                        page_end=page_number,
                        content=parent_text,
                        section=section,
                        content_type="parent",
                        token_count=count_tokens(parent_text),
                        bounding_box=box,
                    )
                )
                index += 1
                for child_text in _split_by_tokens(
                    parent_text, child_tokens, overlap_tokens
                ):
                    chunks.append(
                        ExtractedChunk(
                            chunk_index=index,
                            page_start=page_number,
                            page_end=page_number,
                            content=child_text,
                            section=section,
                            parent_chunk_index=parent_index,
                            content_type=child_type,
                            token_count=count_tokens(child_text),
                            bounding_box=box,
                        )
                    )
                    index += 1
    return chunks


def extract_pdf(pdf_bytes: bytes) -> tuple[int, list[ExtractedChunk]]:
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            page_count = document.page_count
            pages = _extract_page_blocks(document)
    except Exception as exc:
        raise DocumentPreparationError("pdf_extract_failed") from exc

    child_tokens = int(os.environ.get("CHAT_CHILD_CHUNK_TOKENS", "600"))
    parent_tokens = int(os.environ.get("CHAT_PARENT_CHUNK_TOKENS", "1500"))
    overlap_tokens = int(os.environ.get("CHAT_CHUNK_OVERLAP_TOKENS", "100"))
    if (
        child_tokens < 100
        or parent_tokens < child_tokens
        or overlap_tokens >= child_tokens
    ):
        raise DocumentPreparationError("chunk_configuration_invalid")
    chunks = chunk_structured_pages(
        pages,
        child_tokens=child_tokens,
        parent_tokens=parent_tokens,
        overlap_tokens=overlap_tokens,
    )
    children = [chunk for chunk in chunks if chunk.content_type != "parent"]
    if not children or sum(len(chunk.content) for chunk in children) < 1000:
        raise DocumentPreparationError("pdf_text_unavailable")
    return page_count, chunks


def render_pdf_pages(
    pdf_bytes: bytes, page_numbers: list[int]
) -> list[dict[str, object]]:
    rendered: list[dict[str, object]] = []
    scale = min(2.0, max(1.0, float(os.environ.get("CHAT_VISUAL_PAGE_SCALE", "1.5"))))
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            for page_number in page_numbers:
                if page_number < 1 or page_number > document.page_count:
                    continue
                pixmap = document[page_number - 1].get_pixmap(
                    matrix=fitz.Matrix(scale, scale), alpha=False
                )
                encoded = base64.b64encode(pixmap.tobytes("png")).decode("ascii")
                rendered.append(
                    {
                        "page_number": page_number,
                        "data_url": f"data:image/png;base64,{encoded}",
                    }
                )
    except Exception as exc:
        raise DocumentPreparationError("pdf_render_failed") from exc
    return rendered


async def embed_extracted_chunks(
    chunks: list[ExtractedChunk],
) -> tuple[dict[int, list[float]], str | None]:
    if not embeddings_enabled():
        return {}, None
    children = [chunk for chunk in chunks if chunk.content_type != "parent"]
    try:
        config = get_embedding_config()
    except ProviderConfigurationError as exc:
        raise DocumentPreparationError("embedding_configuration_invalid") from exc
    batch_size = max(
        1, min(128, int(os.environ.get("CHAT_EMBEDDING_BATCH_SIZE", "32")))
    )
    vectors: dict[int, list[float]] = {}
    try:
        for start in range(0, len(children), batch_size):
            batch = children[start : start + batch_size]
            await reserve_global_provider_budget(
                sum(max(1, chunk.token_count) for chunk in batch), requests=1
            )
            embedded = await create_embeddings(
                [chunk.content for chunk in batch], config
            )
            vectors.update(
                (chunk.chunk_index, vector)
                for chunk, vector in zip(batch, embedded, strict=True)
            )
    except (GlobalCostLimitExceeded, QuotaConfigurationError) as exc:
        raise DocumentPreparationError(exc.code) from exc
    except ProviderRequestError as exc:
        raise DocumentPreparationError("embedding_failed") from exc
    return vectors, config.model


async def queue_document(paper_id: str) -> str:
    async with get_session_factory()() as db:
        paper = await db.get(Paper, paper_id)
        if not paper:
            raise DocumentPreparationError("paper_not_found")
        await db.execute(
            pg_insert(PaperDocument)
            .values(paper_id=paper_id, status="queued")
            .on_conflict_do_nothing(index_elements=[PaperDocument.paper_id])
        )
        await db.commit()
        document = (
            await db.execute(
                select(PaperDocument)
                .where(PaperDocument.paper_id == paper_id)
                .with_for_update()
            )
        ).scalar_one()
        now = datetime.now(timezone.utc)
        if document.status == "ready" and document_is_current(document):
            document.last_accessed_at = now
            await db.commit()
            return "ready"
        if document.status == "preparing" and document.updated_at:
            updated = document.updated_at
            if updated.tzinfo is None:
                updated = updated.replace(tzinfo=timezone.utc)
            if now - updated < _STALE_AFTER:
                await db.rollback()
                return "preparing"
        document.status = "preparing"
        document.error_code = None
        await db.commit()
        return "queued"


async def prepare_document(paper_id: str) -> None:
    async with _PREPARE_SEMAPHORE:
        async with get_session_factory()() as db:
            paper = await db.get(Paper, paper_id)
            document = await db.get(PaperDocument, paper_id)
            if not paper or not document:
                return
            if document.status == "ready" and document_is_current(document):
                return
            document.status = "preparing"
            document.error_code = None
            await db.commit()

            try:
                url = resolve_pdf_url(paper)
                if not url:
                    raise DocumentPreparationError("pdf_url_missing")
                pdf_bytes = await download_pdf(url)
                page_count, chunks = await asyncio.to_thread(extract_pdf, pdf_bytes)
                embeddings, embedding_model = await embed_extracted_chunks(chunks)
                digest = hashlib.sha256(pdf_bytes).hexdigest()

                await db.execute(
                    delete(PaperChunk).where(PaperChunk.paper_id == paper_id)
                )
                for chunk in chunks:
                    db.add(
                        PaperChunk(
                            paper_id=paper_id,
                            chunk_index=chunk.chunk_index,
                            page_start=chunk.page_start,
                            page_end=chunk.page_end,
                            section=chunk.section,
                            content=chunk.content,
                            char_count=len(chunk.content),
                            token_count=chunk.token_count,
                            parent_chunk_index=chunk.parent_chunk_index,
                            content_type=chunk.content_type,
                            embedding=embeddings.get(chunk.chunk_index),
                            embedding_model=(
                                embedding_model
                                if chunk.chunk_index in embeddings
                                else None
                            ),
                            bounding_box=chunk.bounding_box,
                        )
                    )
                await db.flush()
                document.source_url = url
                document.content_hash = digest
                document.page_count = page_count
                document.chunk_count = sum(
                    chunk.content_type != "parent" for chunk in chunks
                )
                document.extractor_version = EXTRACTOR_VERSION
                document.embedding_model = embedding_model
                document.embedding_dimensions = (
                    len(next(iter(embeddings.values()))) if embeddings else 0
                )
                document.status = "ready"
                document.error_code = None
                document.prepared_at = datetime.now(timezone.utc)
                document.last_accessed_at = datetime.now(timezone.utc)
                await db.commit()
            except DocumentPreparationError as exc:
                await db.rollback()
                document = await db.get(PaperDocument, paper_id)
                if document:
                    document.status = "failed"
                    document.error_code = exc.code
                    await db.commit()
            except Exception:
                log.exception("Document preparation failed for %s", paper_id)
                await db.rollback()
                document = await db.get(PaperDocument, paper_id)
                if document:
                    document.status = "failed"
                    document.error_code = "document_prepare_failed"
                    await db.commit()
