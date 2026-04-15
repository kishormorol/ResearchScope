"""
Post the Paper of the Day to a Discord channel via webhook.

Replicates the same selection logic as the frontend pickPaperOfTheDay():
  pool = top 150 arXiv papers sorted by paper_score desc
  index = dayOfYear % pool.length
"""
from __future__ import annotations

import json
import os
import sys
import urllib.request
from datetime import datetime, timezone

PAPERS_URL = "https://kishormorol.github.io/ResearchScope/data/papers.json"
ARXIV_VENUES = {"arXiv", "Unknown", "", None}
POOL_SIZE = 150


def pick_paper_of_the_day(papers: list[dict]) -> dict | None:
    arxiv = [p for p in papers if p.get("venue") in ARXIV_VENUES]
    arxiv.sort(key=lambda p: -(p.get("paper_score") or 0))
    pool = arxiv[:POOL_SIZE]
    if not pool:
        return None
    today = datetime.now(timezone.utc)
    start_of_year = datetime(today.year, 1, 1, tzinfo=timezone.utc)
    day_of_year = (today - start_of_year).days
    return pool[day_of_year % len(pool)]


def build_payload(paper: dict) -> dict:
    title = paper.get("title", "Untitled")
    url = paper.get("paper_url") or paper.get("url") or ""
    abstract = (paper.get("abstract") or paper.get("summary") or "")[:300]
    if abstract and not abstract.endswith("…"):
        abstract += "…"
    authors = paper.get("authors") or []
    author_str = ", ".join(authors[:4])
    if len(authors) > 4:
        author_str += f" +{len(authors) - 4}"
    venue = " · ".join(filter(None, [paper.get("venue"), str(paper.get("year") or "")]))
    score = paper.get("paper_score")
    score_str = f"⭐ {score:.1f}/10" if score else ""
    tags = paper.get("tags") or []
    tag_str = " · ".join(f"`{t}`" for t in tags[:4])

    fields = []
    if venue:
        fields.append({"name": "Venue", "value": venue, "inline": True})
    if score_str:
        fields.append({"name": "Score", "value": score_str, "inline": True})
    if tag_str:
        fields.append({"name": "Topics", "value": tag_str, "inline": False})

    embed: dict = {
        "title": f"📄 {title}",
        "description": abstract or "_No abstract available._",
        "color": 0x4F46E5,
        "fields": fields,
        "author": {"name": author_str or "Unknown authors"},
        "footer": {
            "text": (
                f"🔭 ResearchScope · Paper of the Day · "
                f"{datetime.now(timezone.utc).strftime('%B %d, %Y')}"
            )
        },
    }
    if url:
        embed["url"] = url

    return {
        "username": "ResearchScope",
        "embeds": [embed],
    }


def post_to_discord(webhook_url: str, payload: dict) -> None:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "ResearchScopeBot/1.0 (https://github.com/kishormorol/ResearchScope)",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as resp:
            print(f"Posted successfully (HTTP {resp.status})")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        print(f"Discord error {e.code}: {body}", file=sys.stderr)
        raise


def main() -> None:
    webhook_url = os.environ.get("DISCORD_WEBHOOK_URL", "").strip()
    if not webhook_url:
        print("ERROR: DISCORD_WEBHOOK_URL is not set.", file=sys.stderr)
        sys.exit(1)

    print(f"Fetching papers from {PAPERS_URL} …")
    with urllib.request.urlopen(PAPERS_URL, timeout=30) as r:
        papers = json.loads(r.read().decode("utf-8"))
    print(f"Loaded {len(papers)} papers.")

    paper = pick_paper_of_the_day(papers)
    if not paper:
        print("No arXiv papers found — nothing to post.", file=sys.stderr)
        sys.exit(1)

    print(f"Paper of the Day: {paper.get('title')}")
    payload = build_payload(paper)
    post_to_discord(webhook_url, payload)


if __name__ == "__main__":
    main()
