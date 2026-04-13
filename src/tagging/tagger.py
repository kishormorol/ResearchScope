"""
Paper tagger: assigns topic tags and detects paper_type from text.
Topics are loaded from config/topics.yaml when available; the built-in
keyword table is used as fallback so the module works without PyYAML.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from src.normalization.schema import Paper


# ── Config ────────────────────────────────────────────────────────────────────

def _load_topics() -> dict[str, Any]:
    cfg_path = Path(__file__).parent.parent.parent / "config" / "topics.yaml"
    try:
        import yaml  # type: ignore
        with open(cfg_path, encoding="utf-8") as fh:
            return yaml.safe_load(fh) or {}
    except Exception:
        pass
    return {}


# ── Built-in tag rules (pattern → human-readable topic) ──────────────────────
# Ordered from most specific to most general. Each paper can match multiple.
# Avoid abbreviations — use full names throughout.

_BUILTIN_RULES: list[tuple[str, str]] = [
    # ── Large Language Models ──────────────────────────────────────────────────
    (r"large language model|llm\b|gpt.?\d|chatgpt|chat model|instruction.tun|instruction follow",
     "Large Language Models"),
    (r"reasoning|chain.of.thought|cot\b|step.by.step reasoning|logical reasoning|math reasoning",
     "Reasoning & Chain-of-Thought"),
    (r"in.context learning|few.shot|zero.shot prompting|prompt engineering|prompt tuning",
     "Prompting & In-Context Learning"),
    (r"hallucination|factuality|grounding|faithfulness|factual consistency",
     "Factuality & Hallucination"),
    (r"long.context|extended context|context window|long document|context length",
     "Long-Context Modeling"),
    (r"mixture of experts|moe\b|sparse model|sparse activation",
     "Mixture of Experts"),
    (r"state space model|mamba\b|ssm\b|linear recurrence|selective state",
     "State Space Models"),

    # ── Fine-tuning & Alignment ────────────────────────────────────────────────
    (r"reinforcement learning from human feedback|rlhf\b|reward model|preference learning|dpo\b|ppo\b.*align",
     "RLHF & Preference Alignment"),
    (r"fine.tun|lora\b|peft\b|adapter\b.*train|parameter.efficient",
     "Fine-Tuning & PEFT"),
    (r"ai safety|alignment|red teaming|constitutional ai|value alignment|jailbreak",
     "AI Safety & Alignment"),

    # ── Agents & Tool Use ─────────────────────────────────────────────────────
    (r"autonomous agent|ai agent|agent framework|tool use|function calling|react\b.*agent|agentic",
     "AI Agents & Tool Use"),
    (r"retrieval.augmented generation|retrieval augmented|rag\b|dense retrieval|passage retrieval",
     "Retrieval-Augmented Generation"),

    # ── Multimodal ────────────────────────────────────────────────────────────
    (r"vision.language model|visual language|vqa\b|clip\b|llava\b|visual question|image.text",
     "Vision-Language Models"),
    (r"multimodal|cross.modal|audio.visual|video.language|multi.modal",
     "Multimodal Learning"),
    (r"text.to.image|image generation|image synthesis|stable diffusion|dall.e|imagen\b",
     "Text-to-Image Generation"),
    (r"video generation|video understanding|video captioning|video question|temporal visual",
     "Video Understanding & Generation"),

    # ── Computer Vision ───────────────────────────────────────────────────────
    (r"object detection|image classification|semantic segmentation|instance segmentation",
     "Object Detection & Segmentation"),
    (r"3d (understanding|reconstruction|generation|point cloud|scene)|nerf\b|gaussian splatting",
     "3D Vision & Scene Understanding"),
    (r"diffusion model|denoising diffusion|score.based generative|ddpm\b|latent diffusion",
     "Diffusion Models"),

    # ── NLP Core Tasks ────────────────────────────────────────────────────────
    (r"machine translation|neural machine translation|nmt\b|low.resource translation",
     "Machine Translation"),
    (r"question answering|reading comprehension|open.domain qa|closed.book qa",
     "Question Answering"),
    (r"summarization|abstractive summarization|extractive summarization|document summarization",
     "Text Summarization"),
    (r"information extraction|named entity recognition|ner\b|relation extraction|event extraction",
     "Information Extraction"),
    (r"sentiment analysis|opinion mining|stance detection|aspect.based sentiment",
     "Sentiment & Opinion Analysis"),
    (r"text classification|document classification|intent detection|topic classification",
     "Text Classification"),
    (r"dialogue|conversation|chatbot|open.domain dialogue|task.oriented dialogue",
     "Dialogue Systems"),
    (r"text generation|natural language generation|nlg\b|story generation|data.to.text",
     "Natural Language Generation"),
    (r"information retrieval|document ranking|search engine|bm25\b|dense retrieval|neural ir",
     "Information Retrieval"),

    # ── Architectures ─────────────────────────────────────────────────────────
    (r"transformer|self[- ]attention|multi[- ]head attention|attention mechanism",
     "Transformer Architectures"),
    (r"graph neural network|graph convolution|gnn\b|gcn\b|gat\b|message passing",
     "Graph Neural Networks"),

    # ── Training & Efficiency ─────────────────────────────────────────────────
    (r"knowledge distillation|model compression|pruning|quantization|quantised",
     "Model Compression & Efficiency"),
    (r"federated learning|privacy.preserving|differential privacy|secure aggregation",
     "Federated & Privacy-Preserving Learning"),
    (r"continual learning|catastrophic forgetting|lifelong learning|incremental learning",
     "Continual Learning"),
    (r"contrastive learning|self.supervised|representation learning|pretraining|pre.training",
     "Self-Supervised & Contrastive Learning"),
    (r"reinforcement learning|reward shaping|policy gradient|q.learning|dqn\b|actor.critic",
     "Reinforcement Learning"),

    # ── Speech & Audio ────────────────────────────────────────────────────────
    (r"speech recognition|automatic speech|asr\b|whisper\b|speech transcription",
     "Speech Recognition"),
    (r"text.to.speech|speech synthesis|tts\b|voice cloning|neural speech",
     "Speech Synthesis"),

    # ── Code & Software ───────────────────────────────────────────────────────
    (r"code generation|program synthesis|code completion|codex\b|copilot|software engineer.*agent",
     "Code Generation & Synthesis"),

    # ── Domain Applications ───────────────────────────────────────────────────
    (r"biomedical|clinical|medical nlp|electronic health|drug discovery|genomic|protein",
     "Biomedical & Clinical AI"),
    (r"legal (nlp|ai|text|document)|contract analysis|legal reasoning",
     "Legal AI"),
    (r"robotic|embodied (ai|agent)|manipulation|navigation.*robot|sim.to.real",
     "Robotics & Embodied AI"),
    (r"table (understanding|qa|parsing)|structured (data|prediction)|tabular",
     "Structured Data & Tables"),
    (r"document (understanding|layout|parsing)|ocr\b|visually rich document",
     "Document Understanding"),
    (r"knowledge graph|ontology|knowledge base|entity link|wikidata\b|knowledge representation",
     "Knowledge Graphs & Representation"),

    # ── Evaluation & Robustness ───────────────────────────────────────────────
    (r"adversarial (attack|example|robustness|training)|robust(ness)? to",
     "Adversarial Robustness"),
    (r"bias|fairness|gender bias|racial bias|toxic|hate speech|social bias",
     "Bias, Fairness & Ethics"),
    (r"interpretab|explainab|attention visuali|saliency|feature importance",
     "Interpretability & Explainability"),
    (r"benchmark|evaluation framework|leaderboard|human evaluation|automatic evaluation",
     "Benchmarking & Evaluation"),

    # ── Embeddings ────────────────────────────────────────────────────────────
    (r"word embedding|sentence embedding|text embedding|semantic similarity|dense vector",
     "Text Embeddings & Semantic Similarity"),
]

_COMPILED_TAGS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(p, re.IGNORECASE), tag) for p, tag in _BUILTIN_RULES
]


# ── Paper-type rules ──────────────────────────────────────────────────────────

_TYPE_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"\bsurvey\b|\boverview\b|\bcomprehensive review\b",      re.IGNORECASE), "survey"),
    (re.compile(r"\bbenchmark\b|\bleaderboard\b|\bcomparative study\b",   re.IGNORECASE), "benchmark"),
    (re.compile(r"\bdataset\b|\bcorpus\b|\bannotation\b|\bcollection\b",  re.IGNORECASE), "dataset"),
    (re.compile(r"\bsystems?\b.*\bdesign\b|\bscalable\b|\binfrastructure\b|\bdeployment\b",
                re.IGNORECASE), "systems"),
    (re.compile(r"\btheorem\b|\bproof\b|\blemma\b|\bconvergence\b",       re.IGNORECASE), "theory"),
    (re.compile(r"\btutorial\b|\bprimer\b|\bintroduction to\b|\bgetting started\b",
                re.IGNORECASE), "tutorial"),
    (re.compile(r"\bposition paper\b|\bwe argue\b|\bwe call for\b",       re.IGNORECASE), "position"),
    (re.compile(r"\bnegative result\b|\bfailed\b|\bdoes not\b.*improve",  re.IGNORECASE), "negative_result"),
    (re.compile(r"\breplication\b|\breproduc\b",                          re.IGNORECASE), "replication"),
    (re.compile(r"\bwe propose\b|\bwe introduce\b|\bnovel method\b|\bnew (model|approach|architecture)\b",
                re.IGNORECASE), "methods"),
    (re.compile(r"\bwe (conduct|run|perform) experiment|\bempirical (study|analysis|evaluation)\b",
                re.IGNORECASE), "empirical"),
]


class PaperTagger:
    """
    Enrich paper.tags from title+abstract keywords.
    Detect paper.paper_type from structural language cues.
    """

    def tag(self, paper: Paper) -> Paper:
        haystack = f"{paper.title} {paper.abstract}"
        existing = set(paper.tags)

        for pattern, tag_name in _COMPILED_TAGS:
            if tag_name not in existing and pattern.search(haystack):
                existing.add(tag_name)

        paper.tags = sorted(existing)

        if not paper.paper_type:
            paper.paper_type = self._detect_type(haystack)

        return paper

    @staticmethod
    def _detect_type(text: str) -> str:
        for pattern, ptype in _TYPE_RULES:
            if pattern.search(text):
                return ptype
        return "methods"  # sensible default
