"""Write the five reader-facing paper fields with an open LLM (Gemma 4), via vLLM.

The template generator in src/content/generator.py fills summary, key_contribution,
one_line_takeaway, plain_english_explanation and why_it_matters by copying abstract
sentences or filling a template. This script replaces them with model-written text,
grounded only in the title and abstract, and writes one JSON line per paper:

    {"id", "abstract_sha", "model", "prompt_version", "fields": {...}, "flags": [...]}

The pipeline reads that file as a cache (src/content/llm_cache.py); an entry is used
only while the paper's abstract hash still matches.

Two engines: vLLM (default; fast, JSON-constrained decoding) needs an Ampere or newer
GPU, because Gemma 4's 512-wide attention heads overflow a T4's shared memory in vLLM's
Triton kernel. --engine hf uses plain transformers, which is slow but runs on a T4, and
is enough for a pilot. Resumable: papers already in --out are skipped.

    python enrich.py --papers papers.parquet --out llm_fields.jsonl --limit 50
    python enrich.py --papers papers.parquet --out llm_fields.jsonl --shard 0/4
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path

PROMPT_VERSION = 1

SYSTEM = """You write short, accurate descriptions of research papers for a \
paper-discovery site. You are given only a paper's title and abstract. Use nothing \
else: do not add \
facts, numbers, datasets, or claims that are not in the abstract. If the abstract \
does not say something, leave it out rather than guess. Write in plain, specific \
language. No hype words (groundbreaking, revolutionary, novel, cutting-edge), no \
"This paper" openings, no emojis."""

TASK = """Title: {title}
Venue: {venue} {year}
Abstract: {abstract}

Return JSON with these fields:
- "summary": 2-3 sentences: the problem, the approach, and the main result as \
stated.
- "key_contribution": 1 sentence naming the main new thing the authors contribute.
- "one_line_takeaway": one sentence, at most 25 words, for a newsletter reader.
- "plain_english_explanation": 2-3 sentences a smart non-specialist can follow; \
explain or avoid jargon.
- "why_it_matters": 1-2 sentences on who benefits or what it enables, only as far as\
 the abstract supports."""

FIELDS = [
    "summary",
    "key_contribution",
    "one_line_takeaway",
    "plain_english_explanation",
    "why_it_matters",
]

SCHEMA = {
    "type": "object",
    "properties": {f: {"type": "string"} for f in FIELDS},
    "required": FIELDS,
    "additionalProperties": False,
}

NUM = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)*%?")


def abstract_sha(title: str, abstract: str) -> str:
    return hashlib.sha256(f"{title}\n{abstract}".encode()).hexdigest()[:16]


def check(fields: dict, title: str, abstract: str) -> list[str]:
    """Flags for a human or a filter; an empty list means the output looks sound."""
    flags = []
    source = f"{title} {abstract}".replace("\\", "")  # abstracts keep LaTeX: 17\\%
    for f in FIELDS:
        text = (fields.get(f) or "").strip()
        if not text:
            flags.append(f"empty:{f}")
            continue
        invented = [n for n in NUM.findall(text) if n not in source]
        if invented:
            flags.append(f"numbers_not_in_abstract:{f}:{','.join(invented[:3])}")
        if text[:60] and text[:60] in abstract:
            flags.append(f"copied_from_abstract:{f}")
    if len((fields.get("one_line_takeaway") or "").split()) > 30:
        flags.append("takeaway_too_long")
    return flags


def load_papers(path: str):
    import pandas as pd

    df = (
        pd.read_parquet(path)
        if path.endswith(".parquet")
        else pd.read_json(path, lines=path.endswith(".jsonl"))
    )
    df = df[df.abstract.fillna("").str.len() >= 100]
    return (
        df[["id", "title", "abstract", "venue", "year"]].fillna("").to_dict("records")
    )


def sampling_params(max_tokens: int):
    """JSON-constrained decoding; the vLLM API for it moved between versions."""
    from vllm import SamplingParams

    base = dict(temperature=0.2, top_p=0.95, max_tokens=max_tokens)
    try:
        from vllm.sampling_params import StructuredOutputsParams

        return SamplingParams(
            **base, structured_outputs=StructuredOutputsParams(json=SCHEMA)
        )
    except ImportError:
        from vllm.sampling_params import GuidedDecodingParams

        return SamplingParams(**base, guided_decoding=GuidedDecodingParams(json=SCHEMA))


def parse_json(text: str) -> dict:
    """The object in a reply; the hf engine is not constrained, so it may add fences."""
    start, end = text.find("{"), text.rfind("}")
    return json.loads(text[start : end + 1] if start >= 0 else text)


class VLLMEngine:
    def __init__(self, args):
        import torch
        from vllm import LLM

        tp = args.tp or max(1, torch.cuda.device_count())
        self.llm = LLM(
            model=args.model,
            tensor_parallel_size=tp,
            dtype=args.dtype,
            max_model_len=args.max_model_len,
            gpu_memory_utilization=0.92,
        )
        self.params = sampling_params(args.max_tokens)

    def generate(self, convs: list) -> list[str]:
        return [
            r.outputs[0].text for r in self.llm.chat(convs, self.params, use_tqdm=False)
        ]


class HFEngine:
    def __init__(self, args):
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.tok = AutoTokenizer.from_pretrained(args.model, padding_side="left")
        dtype = {"float16": torch.float16, "bfloat16": torch.bfloat16}.get(
            args.dtype, "auto"
        )
        # "balanced" splits layers evenly; "auto" fills GPU 0 first, leaving no room
        # for activations on it.
        kw = dict(torch_dtype=dtype, device_map="balanced", attn_implementation="sdpa")
        try:
            self.model = AutoModelForCausalLM.from_pretrained(args.model, **kw)
        except ValueError:  # multimodal checkpoints (Gemma 4) are image-text-to-text
            from transformers import AutoModelForImageTextToText
            self.model = AutoModelForImageTextToText.from_pretrained(args.model, **kw)
        self.max_tokens = args.max_tokens

    def generate(self, convs: list) -> list[str]:
        import torch

        prompts = [
            self.tok.apply_chat_template(c, tokenize=False, add_generation_prompt=True)
            for c in convs
        ]
        enc = self.tok(prompts, return_tensors="pt", padding=True).to(self.model.device)
        with torch.no_grad():
            out = self.model.generate(
                **enc,
                max_new_tokens=self.max_tokens,
                do_sample=True,
                temperature=0.2,
                top_p=0.95,
            )
        return self.tok.batch_decode(
            out[:, enc.input_ids.shape[1] :], skip_special_tokens=True
        )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument(
        "--papers", required=True, help="papers.parquet / .jsonl / _db.json"
    )
    ap.add_argument("--out", required=True, help="output JSONL; appended to, resumable")
    ap.add_argument("--model", required=True, help="local path or HF id of the model")
    ap.add_argument("--model-name", default=None, help="name recorded in the output")
    ap.add_argument(
        "--limit", type=int, default=0, help="stop after this many new papers"
    )
    ap.add_argument("--shard", default="0/1", help="i/n: take every n-th paper from i")
    ap.add_argument("--batch", type=int, default=512, help="papers per vLLM call")
    ap.add_argument("--max-tokens", type=int, default=700)
    ap.add_argument(
        "--tp", type=int, default=0, help="tensor parallel size; 0 = all GPUs"
    )
    ap.add_argument(
        "--dtype", default="auto", help="float16 on T4/P100, auto elsewhere"
    )
    ap.add_argument("--max-model-len", type=int, default=4096)
    ap.add_argument("--engine", choices=["vllm", "hf"], default="vllm")
    args = ap.parse_args()

    out = Path(args.out)
    done = set()
    if out.exists():
        with out.open() as fh:
            done = {json.loads(line)["id"] for line in fh if line.strip()}

    i, n = map(int, args.shard.split("/"))
    papers = [
        p
        for k, p in enumerate(load_papers(args.papers))
        if k % n == i and p["id"] not in done
    ]
    if args.limit:
        papers = papers[: args.limit]
    print(
        f"{len(done)} already done, {len(papers)} to go (shard {args.shard})",
        flush=True,
    )
    if not papers:
        return

    engine = (VLLMEngine if args.engine == "vllm" else HFEngine)(args)
    name = args.model_name or os.path.basename(args.model.rstrip("/"))

    t0, n_ok, n_flag = time.time(), 0, 0
    with out.open("a") as fh:
        for start in range(0, len(papers), args.batch):
            batch = papers[start : start + args.batch]
            convs = [
                [
                    {"role": "system", "content": SYSTEM},
                    {"role": "user", "content": TASK.format(**p)},
                ]
                for p in batch
            ]
            for p, text in zip(batch, engine.generate(convs)):
                try:
                    fields = {
                        f: str(v).strip()
                        for f, v in parse_json(text).items()
                        if f in FIELDS
                    }
                except (json.JSONDecodeError, AttributeError):
                    fields, flags = {"_raw": text[:2000]}, ["invalid_json"]
                else:
                    flags = check(fields, p["title"], p["abstract"])
                n_ok += not flags
                n_flag += bool(flags)
                fh.write(
                    json.dumps(
                        {
                            "id": p["id"],
                            "abstract_sha": abstract_sha(p["title"], p["abstract"]),
                            "model": name,
                            "prompt_version": PROMPT_VERSION,
                            "fields": fields,
                            "flags": flags,
                        },
                        ensure_ascii=False,
                    )
                    + "\n"
                )
            fh.flush()
            done_n = start + len(batch)
            rate = done_n / (time.time() - t0)
            print(
                f"{done_n}/{len(papers)} papers, {rate:.2f}/s, "
                f"eta {(len(papers) - done_n) / rate / 60:.0f} min, flagged {n_flag}",
                flush=True,
            )
    print(f"done: {n_ok} clean, {n_flag} flagged", file=sys.stderr)


if __name__ == "__main__":
    main()
