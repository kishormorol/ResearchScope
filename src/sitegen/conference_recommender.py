"""Build static data for the Conference Recommender.

The recommender index is generated from existing ResearchScope artifacts:
- conference paper JSON files for venue profiles, keywords, and examples
- the static deadlines page for current deadline metadata

No runtime API is used by the frontend.
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import os
import subprocess
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sklearn.feature_extraction.text import TfidfVectorizer


ROOT = Path(__file__).resolve().parents[2]
LEGACY_OUTPUT = ROOT / "data" / "conference_recommender.json"
DEFAULT_OUTPUT = ROOT / "site" / "data" / "conference_recommender.json"
SITE_OUTPUT = DEFAULT_OUTPUT
DEADLINES_PAGE = ROOT / "site" / "deadlines.html"

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "by", "can", "for", "from",
    "has", "have", "in", "into", "is", "it", "its", "may", "method", "model",
    "models", "of", "on", "or", "our", "paper", "propose", "show", "study",
    "that", "the", "their", "these", "this", "to", "use", "using", "via", "we",
    "with", "which", "new", "novel", "methods", "task", "tasks", "achieve",
    "achieves", "approach", "approaches", "based", "different", "first",
    "however", "results",
}

IGNORED_VENUES = {"", "arxiv", "corr", "unknown", "openreview", "jmlr", "tacl", "tpami"}

FIELD_LABELS = {
    "any": "Any field",
    "ML": "Machine Learning",
    "NLP": "NLP / Language",
    "CV": "Computer Vision",
    "AI": "AI / Agents / Reasoning",
    "HCI": "HCI / Human-AI Interaction",
    "IR": "Information Retrieval",
    "DM": "Data Mining",
    "SE": "Software Engineering",
}

FIELD_HINTS = {
    "ML": {
        "machine", "learning", "optimization", "representation", "bayesian",
        "reinforcement", "generalization", "training", "gradient",
    },
    "NLP": {
        "language", "nlp", "translation", "linguistic", "multilingual",
        "summarization", "dialogue", "question", "answering", "llm",
    },
    "CV": {
        "vision", "image", "video", "visual", "segmentation", "detection",
        "recognition", "3d", "geometry", "diffusion",
    },
    "AI": {
        "agent", "planning", "reasoning", "knowledge", "search", "decision",
        "autonomous", "logic", "artificial",
    },
    "HCI": {
        "human", "user", "interface", "interaction", "usability", "study",
        "participants", "design", "qualitative",
    },
    "IR": {
        "retrieval", "search", "ranking", "query", "relevance", "recommendation",
        "recommendations", "rag",
    },
    "DM": {
        "mining", "graph", "graphs", "knowledge", "discovery", "anomaly",
        "causal", "large", "scale",
    },
    "SE": {
        "software", "program", "code", "testing", "developer", "debugging",
        "repair", "repository", "repositories",
    },
}

FIELD_EXPECTATIONS = {
    "ML": [
        "A clearly scoped learning problem with strong empirical or theoretical support.",
        "Baselines, ablations, and evaluation settings that isolate the contribution.",
        "Reproducibility details for data, training, hyperparameters, and limitations.",
    ],
    "NLP": [
        "Task framing, datasets, and metrics that match current NLP practice.",
        "Comparisons against recent language-model or task-specific baselines.",
        "Error analysis and discussion of data, multilingual, safety, or evaluation limits.",
    ],
    "CV": [
        "Strong visual benchmarks with quantitative and qualitative evidence.",
        "Ablations and comparisons against current vision or multimodal systems.",
        "Failure cases, dataset coverage, and limitations for real-world claims.",
    ],
    "AI": [
        "A clear AI problem formulation with novelty beyond implementation detail.",
        "Evaluation that shows the method works beyond narrow or toy settings.",
        "Positioning against planning, reasoning, agents, or knowledge-representation work.",
    ],
    "HCI": [
        "A human-centered research question with an appropriate study design.",
        "Transparent participant protocol, analysis method, and ethical handling.",
        "Design implications grounded in the evidence rather than speculation.",
    ],
    "IR": [
        "Retrieval or ranking evaluation with accepted IR metrics and datasets.",
        "Comparisons across classical, neural, and efficiency-aware baselines.",
        "Analysis of relevance, query behavior, robustness, and failure cases.",
    ],
    "DM": [
        "Large-scale data-mining evidence with realistic datasets and baselines.",
        "A clear value proposition over standard predictive modeling.",
        "Scalability, robustness, and deployment-aware analysis where relevant.",
    ],
    "SE": [
        "A realistic software-engineering task with meaningful artifacts or users.",
        "Evaluation on repositories, developer workflows, tests, or maintenance settings.",
        "Clear implications for engineering practice and tool adoption.",
    ],
}

GENERIC_EXPECTATIONS = [
    "A clear problem statement, contribution, and relation to recent venue work.",
    "Strong baselines, careful evaluation, and evidence that supports the main claims.",
    "Limitations, reproducibility details, and a concise explanation of reviewer-facing novelty.",
]


def _tokenize(text: str) -> list[str]:
    words = re.findall(r"[a-zA-Z][a-zA-Z0-9+-]{2,}", text.lower())
    return [w for w in words if w not in STOP_WORDS and len(w) <= 32]


def _load_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as fh:
        data = json.load(fh)
    return data if isinstance(data, list) else []


def _load_paper_sources() -> list[dict[str, Any]]:
    paths = [
        ROOT / "data" / "conferences.json",
        ROOT / "data" / "conferences_db.json",
        ROOT / "site" / "data" / "conferences.json",
        ROOT / "site" / "data" / "conferences_db.json",
        ROOT / "data" / "papers.json",
        ROOT / "site" / "data" / "papers.json",
    ]
    papers: dict[str, dict[str, Any]] = {}
    for path in paths:
        for paper in _load_json(path):
            if not isinstance(paper, dict):
                continue
            venue = _clean_venue(paper.get("venue"))
            if not venue or venue.lower() in IGNORED_VENUES:
                continue
            if str(paper.get("source_type", "")).lower() not in {"", "conference"}:
                continue
            key = str(paper.get("id") or paper.get("paper_url") or paper.get("url") or f"{venue}:{paper.get('title', '')}")
            papers[key] = paper
    return list(papers.values())


def _clean_venue(value: Any) -> str:
    venue = str(value or "").strip()
    return re.sub(r"\s+", " ", venue)


def _venue_id(short: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", short.lower()).strip("-")


def _paper_text(paper: dict[str, Any]) -> str:
    tags = " ".join(str(t) for t in paper.get("tags", []) if t)
    return " ".join([
        str(paper.get("title", "")),
        str(paper.get("abstract", "")),
        str(paper.get("summary", "")),
        str(paper.get("key_contribution", "")),
        str(paper.get("one_line_takeaway", "")),
        tags,
    ])


def _extract_deadlines(path: Path) -> dict[str, dict[str, Any]]:
    log = logging.getLogger(__name__)
    if not path.exists():
        log.warning("Conference recommender: deadlines source not found at %s", path)
        return {}
    text = path.read_text(encoding="utf-8")
    start = text.find("const DEADLINES")
    if start < 0:
        log.warning("Conference recommender: DEADLINES constant not found in %s", path)
        return {}
    array_start = text.find("[", start)
    if array_start < 0:
        log.warning("Conference recommender: DEADLINES array start not found in %s", path)
        return {}

    body_chars: list[str] = []
    depth = 1
    in_string: str | None = None
    escaped = False
    for char in text[array_start + 1:]:
        if in_string:
            body_chars.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            continue

        if char in {"'", '"'}:
            in_string = char
            body_chars.append(char)
            continue
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                break
        body_chars.append(char)

    body = "".join(body_chars)
    objects: list[str] = []
    current: list[str] = []
    depth = 0
    in_string = None
    escaped = False
    for char in body:
        if in_string:
            if depth:
                current.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == in_string:
                in_string = None
            continue

        if char in {"'", '"'}:
            in_string = char
            if depth:
                current.append(char)
            continue
        if char == "{":
            if depth == 0:
                current = []
            else:
                current.append(char)
            depth += 1
            continue
        if char == "}":
            depth -= 1
            if depth == 0:
                objects.append("".join(current))
                current = []
            elif depth > 0:
                current.append(char)
            continue
        if depth:
            current.append(char)

    deadlines: dict[str, dict[str, Any]] = {}
    for obj in objects:
        row: dict[str, Any] = {}
        for key, raw in re.findall(r"(\w+)\s*:\s*(\"[^\"]*\"|'[^']*'|true|false)", obj):
            if raw in {"true", "false"}:
                row[key] = raw == "true"
            else:
                row[key] = raw[1:-1]
        short = str(row.get("short", "")).strip()
        if short:
            deadlines[short.lower()] = row
    if not deadlines:
        log.warning("Conference recommender: extracted zero deadlines from %s", path)
    return deadlines


def _infer_field(deadline: dict[str, Any] | None, papers: list[dict[str, Any]]) -> str:
    if deadline and deadline.get("area") in FIELD_LABELS:
        return str(deadline["area"])

    counter: Counter[str] = Counter()
    for paper in papers[:120]:
        counter.update(_tokenize(_paper_text(paper)))
        counter.update(_tokenize(" ".join(str(t) for t in paper.get("tags", []) if t)))

    scores = {
        field: sum(counter[token] for token in tokens)
        for field, tokens in FIELD_HINTS.items()
    }
    best_field, best_score = max(scores.items(), key=lambda item: item[1])
    return best_field if best_score > 0 else "ML"


def _venue_documents(papers: list[dict[str, Any]], field: str) -> list[str]:
    return [_paper_text(paper).strip() for paper in papers]


def _derive_keywords(papers: list[dict[str, Any]], field: str, limit: int = 85) -> list[str]:
    term_counter: Counter[str] = Counter()
    phrase_counter: Counter[str] = Counter()

    for paper in papers:
        text = _paper_text(paper)
        tokens = _tokenize(text)
        term_counter.update(tokens)
        tag_tokens = []
        for tag in paper.get("tags", []) or []:
            tag_text = str(tag).strip().lower()
            if tag_text:
                phrase_counter[tag_text] += 3
                tag_tokens.extend(_tokenize(tag_text))
        term_counter.update(tag_tokens)

        for first, second in zip(tokens, tokens[1:]):
            if first != second:
                phrase_counter[f"{first} {second}"] += 1

    keywords: list[str] = []
    for token in sorted(FIELD_HINTS.get(field, set())):
        keywords.append(token)
    for phrase, _ in phrase_counter.most_common(45):
        if 3 <= len(phrase) <= 56 and phrase not in keywords:
            keywords.append(phrase)
    for term, _ in term_counter.most_common(55):
        if term not in keywords:
            keywords.append(term)
    return keywords[:limit]


def _weighted_from_terms(terms: list[str], base_weight: float = 0.35) -> list[dict[str, Any]]:
    return [
        {"term": term, "weight": round(max(base_weight, 0.01), 4)}
        for term in terms
    ]


def _build_tfidf_profiles(
    venue_documents: dict[str, list[str]],
    fallback_keywords: dict[str, list[str]],
    limit: int = 85,
) -> dict[str, list[dict[str, Any]]]:
    shorts = list(venue_documents)
    if not shorts:
        return {}

    documents: list[str] = []
    document_venues: list[str] = []
    for short in shorts:
        for document in venue_documents[short]:
            if document.strip():
                documents.append(document)
                document_venues.append(short)
    if not documents:
        return {
            short: _weighted_from_terms(fallback_keywords.get(short, [])[:limit])
            for short in shorts
        }

    vectorizer = TfidfVectorizer(
        tokenizer=_tokenize,
        token_pattern=None,
        ngram_range=(1, 2),
        min_df=1,
        max_df=0.92,
        sublinear_tf=True,
        norm="l2",
        max_features=4000,
    )
    matrix = vectorizer.fit_transform(documents)
    feature_names = vectorizer.get_feature_names_out()

    venue_scores: dict[str, Counter[str]] = {short: Counter() for short in shorts}
    for row_index, short in enumerate(document_venues):
        row = matrix.getrow(row_index)
        for feature_index, score in zip(row.indices, row.data):
            venue_scores[short][str(feature_names[feature_index])] += float(score)

    profiles: dict[str, list[dict[str, Any]]] = {}
    for short in shorts:
        scores = venue_scores[short]
        if not scores:
            profiles[short] = _weighted_from_terms(fallback_keywords.get(short, [])[:limit])
            continue

        max_score = scores.most_common(1)[0][1] or 1.0
        weighted_terms: list[dict[str, Any]] = []
        seen: set[str] = set()
        for term, score in scores.most_common(limit):
            term = term.strip()
            if not term or term in seen:
                continue
            seen.add(term)
            weighted_terms.append({
                "term": term,
                "weight": round(float(score) / max_score, 4),
            })

        if len(weighted_terms) < limit:
            for term in fallback_keywords.get(short, []):
                if term not in seen:
                    weighted_terms.append({"term": term, "weight": 0.2})
                    seen.add(term)
                if len(weighted_terms) >= limit:
                    break
        profiles[short] = weighted_terms
    return profiles


def _accepted_papers(papers: list[dict[str, Any]], limit: int = 18) -> list[dict[str, Any]]:
    ranked = sorted(
        papers,
        key=lambda p: (float(p.get("paper_score") or 0), int(p.get("year") or 0)),
        reverse=True,
    )
    accepted = []
    for paper in ranked[:limit]:
        accepted.append({
            "id": paper.get("id", ""),
            "title": paper.get("title", ""),
            "year": paper.get("year", ""),
            "venue": paper.get("venue", ""),
            "url": paper.get("paper_url") or paper.get("url") or "",
            "tags": (paper.get("tags") or [])[:6],
            "abstract": str(paper.get("abstract") or paper.get("summary") or "")[:260],
            "terms": [term for term, _ in Counter(_tokenize(_paper_text(paper))).most_common(32)],
        })
    return accepted


def _rank_for_venue(deadline: dict[str, Any] | None, papers: list[dict[str, Any]]) -> str:
    if deadline and deadline.get("rank"):
        return str(deadline["rank"])
    ranks = Counter(str(p.get("conference_rank", "")).strip() for p in papers if p.get("conference_rank"))
    return ranks.most_common(1)[0][0] if ranks else ""


def _venue_name(short: str, deadline: dict[str, Any] | None) -> str:
    if not deadline or not deadline.get("name"):
        return short
    name = str(deadline["name"]).strip()
    return re.sub(r"\s+20\d{2}\b", "", name).strip() or short


def _deadline_payload(deadline: dict[str, Any] | None) -> dict[str, Any]:
    if not deadline:
        return {}
    keys = [
        "name", "short", "area", "rank", "abstract_deadline", "paper_deadline",
        "notification", "conf_start", "conf_end", "location", "website", "confirmed",
    ]
    return {key: deadline[key] for key in keys if key in deadline and deadline[key] not in {"", None}}


def _expectations(field: str, rank: str, papers: list[dict[str, Any]]) -> list[str]:
    expectations = list(FIELD_EXPECTATIONS.get(field, GENERIC_EXPECTATIONS))
    paper_types = Counter(str(p.get("paper_type", "")).strip() for p in papers if p.get("paper_type"))
    if paper_types:
        dominant = paper_types.most_common(1)[0][0].replace("_", " ")
        expectations.append(f"Recent accepted papers skew toward {dominant}; make that contribution type explicit.")
    if rank == "A*":
        expectations.append("Top-tier selectivity means reviewers will expect novelty, depth, and polished evidence.")
    return expectations[:4]


def build_index() -> dict[str, Any]:
    papers = _load_paper_sources()
    deadlines = _extract_deadlines(DEADLINES_PAGE)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for paper in papers:
        venue = _clean_venue(paper.get("venue"))
        if venue and venue.lower() not in IGNORED_VENUES:
            grouped[venue].append(paper)

    prepared_venues = []
    for short, venue_papers in sorted(grouped.items()):
        deadline = deadlines.get(short.lower())
        if len(venue_papers) < 8 and not deadline:
            continue

        ranked_papers = sorted(
            venue_papers,
            key=lambda p: (float(p.get("paper_score") or 0), int(p.get("year") or 0)),
            reverse=True,
        )
        field = _infer_field(deadline, ranked_papers)
        rank = _rank_for_venue(deadline, ranked_papers)
        fallback_keywords = _derive_keywords(ranked_papers[:250], field)

        prepared_venues.append({
            "id": _venue_id(short),
            "short": short,
            "name": _venue_name(short, deadline),
            "type": "conference",
            "field": field,
            "rank": rank,
            "paper_count": len(venue_papers),
            "fallback_keywords": fallback_keywords,
            "documents": _venue_documents(ranked_papers[:250], field),
            "expectations": _expectations(field, rank, ranked_papers),
            "deadline": _deadline_payload(deadline),
            "accepted_papers": _accepted_papers(ranked_papers),
        })

    weighted_profiles = _build_tfidf_profiles(
        {venue["short"]: venue["documents"] for venue in prepared_venues},
        {venue["short"]: venue["fallback_keywords"] for venue in prepared_venues},
    )
    venue_rows = []
    for venue in prepared_venues:
        weighted_keywords = weighted_profiles.get(venue["short"], [])
        venue_rows.append({
            key: value
            for key, value in venue.items()
            if key not in {"documents", "fallback_keywords"}
        } | {
            "keywords": [item["term"] for item in weighted_keywords],
            "weighted_keywords": weighted_keywords,
        })

    venue_rows.sort(key=lambda v: (1 if v["deadline"].get("paper_deadline") else 0, v["paper_count"]), reverse=True)

    return {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "papers": "site/data conference paper JSON",
            "deadlines": "site/deadlines.html",
            "method": "generated from venue paper aggregates, TfidfVectorizer weighted keywords, and deadline metadata",
        },
        "fields": [{"id": key, "label": label} for key, label in FIELD_LABELS.items()],
        "maturity_options": [
            {"id": "any", "label": "Not sure"},
            {"id": "early", "label": "Early idea / workshop-ready"},
            {"id": "solid", "label": "Solid experiments"},
            {"id": "mature", "label": "Mature conference-ready draft"},
        ],
        "venues": venue_rows,
    }


def validate_index(data: dict[str, Any]) -> None:
    if data.get("schema_version") != 1:
        raise ValueError("schema_version must be 1")
    venues = data.get("venues")
    if not isinstance(venues, list) or len(venues) < 10:
        raise ValueError("venues must contain at least 10 generated conference profiles")
    required = {
        "id", "short", "name", "type", "field", "rank", "paper_count",
        "keywords", "weighted_keywords", "expectations", "deadline", "accepted_papers",
    }
    for venue in venues:
        missing = required - set(venue)
        if missing:
            raise ValueError(f"venue {venue.get('id')} missing fields: {sorted(missing)}")
        if venue["type"] != "conference":
            raise ValueError(f"invalid venue type for {venue['id']}")
        if not venue["keywords"]:
            raise ValueError(f"venue {venue['id']} has no keywords")
        if not venue["weighted_keywords"]:
            raise ValueError(f"venue {venue['id']} has no weighted keywords")
        for keyword in venue["weighted_keywords"]:
            if not {"term", "weight"} <= set(keyword):
                raise ValueError(f"weighted keyword for {venue['id']} has invalid schema")
            if not 0 < float(keyword["weight"]) <= 1:
                raise ValueError(f"weighted keyword for {venue['id']} has invalid weight")
        if not venue["expectations"]:
            raise ValueError(f"venue {venue['id']} has no expectations")
        for paper in venue["accepted_papers"]:
            if not {"title", "year", "url", "terms"} <= set(paper):
                raise ValueError(f"accepted paper for {venue['id']} has invalid schema")


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def maybe_stage_output(path: Path) -> None:
    if os.environ.get("GITHUB_ACTIONS") != "true":
        return
    try:
        subprocess.run(
            ["git", "add", str(path.relative_to(ROOT))],
            cwd=ROOT,
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except (OSError, subprocess.CalledProcessError, ValueError):
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Build Conference Recommender static JSON.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    data = build_index()
    validate_index(data)
    if args.validate_only:
        print(f"validated {len(data['venues'])} generated conference recommender venues")
        return

    write_json(args.output, data)
    print(f"wrote {args.output}")
    maybe_stage_output(args.output)

    if args.output == DEFAULT_OUTPUT and LEGACY_OUTPUT.is_file():
        LEGACY_OUTPUT.unlink()
        print(f"removed stale {LEGACY_OUTPUT}")


if __name__ == "__main__":
    main()
