"""Tests for PaperTagger and DifficultyAssessor."""
from __future__ import annotations

import pytest

from src.difficulty.assessor import DifficultyAssessor
from src.normalization.schema import Paper
from src.tagging.tagger import PaperTagger


def _paper(abstract: str, title: str = "", tags: list[str] | None = None) -> Paper:
    return Paper(id="t1", title=title, abstract=abstract, tags=tags or [])


class TestPaperTagger:
    def setup_method(self):
        self.tagger = PaperTagger()

    def test_transformer_attention_tag(self):
        p = self.tagger.tag(_paper("We propose a transformer with attention mechanism."))
        assert "Transformer Architectures" in p.tags

    def test_llm_tag(self):
        p = self.tagger.tag(_paper("We study large language model alignment."))
        assert "Large Language Models" in p.tags

    def test_llm_abbreviation(self):
        p = self.tagger.tag(_paper("LLM-based systems are becoming widespread."))
        assert "Large Language Models" in p.tags

    def test_diffusion_tag(self):
        p = self.tagger.tag(_paper("We use a diffusion model for image synthesis."))
        assert "Diffusion Models" in p.tags

    def test_rl_tag(self):
        p = self.tagger.tag(_paper("We apply reinforcement learning to robotics."))
        assert "Reinforcement Learning" in p.tags

    def test_gnn_tag(self):
        p = self.tagger.tag(_paper("Graph neural networks for node classification."))
        assert "Graph Neural Networks" in p.tags

    def test_rag_tag(self):
        p = self.tagger.tag(_paper("Retrieval-augmented generation improves QA."))
        assert "Retrieval-Augmented Generation" in p.tags

    def test_code_generation_tag(self):
        p = self.tagger.tag(_paper("code generation with LLM", title="Code Completion"))
        assert "Code Generation & Synthesis" in p.tags

    def test_ai_agents_tag(self):
        p = self.tagger.tag(_paper("We study autonomous agent frameworks with tool use."))
        assert "AI Agents & Tool Use" in p.tags

    def test_ai_safety_tag(self):
        p = self.tagger.tag(_paper("We evaluate hallucination and alignment in language models."))
        assert "AI Safety & Alignment" in p.tags

    def test_existing_tags_preserved(self):
        p = Paper(id="x", abstract="We study transformers.", tags=["NLP"])
        result = self.tagger.tag(p)
        assert "NLP" in result.tags
        assert "Transformer Architectures" in result.tags

    def test_tags_sorted(self):
        p = self.tagger.tag(_paper("reinforcement learning with large language models"))
        assert p.tags == sorted(p.tags)

    def test_no_irrelevant_tags(self):
        p = self.tagger.tag(_paper("We study weather forecasting with CNNs."))
        assert "Large Language Models" not in p.tags
        assert "Reinforcement Learning" not in p.tags

    def test_paper_type_survey(self):
        p = _paper("This survey provides an overview of the field.", title="A Survey")
        self.tagger.tag(p)
        assert p.paper_type == "survey"

    def test_paper_type_benchmark(self):
        p = _paper("We present a benchmark for NLP evaluation tasks.")
        self.tagger.tag(p)
        assert p.paper_type == "benchmark"

    def test_paper_type_dataset(self):
        p = _paper("We release a new corpus with human annotation.")
        self.tagger.tag(p)
        assert p.paper_type == "dataset"

    def test_paper_type_not_overwritten_if_set(self):
        p = _paper("a survey of everything")
        p.paper_type = "benchmark"
        self.tagger.tag(p)
        assert p.paper_type == "benchmark"


class TestDifficultyAssessor:
    def setup_method(self):
        self.assessor = DifficultyAssessor()

    def test_survey_is_l1(self):
        p = _paper("This tutorial provides an introduction to NLP.", title="A Survey of NLP")
        self.assessor.assess(p)
        assert p.difficulty_level == "L1"

    def test_theorem_is_l4(self):
        p = _paper("We prove a theorem and provide a convergence guarantee with regret bounds.")
        self.assessor.assess(p)
        assert p.difficulty_level == "L4"

    def test_default_is_l2(self):
        p = _paper("We evaluate a model on three benchmarks and report accuracy.")
        self.assessor.assess(p)
        assert p.difficulty_level == "L2"

    def test_reason_nonempty(self, sample_paper: Paper):
        self.assessor.assess(sample_paper)
        assert len(sample_paper.difficulty_reason) > 10

    def test_sentiment_without_math_is_l1(self):
        p = _paper("We apply BERT to sentiment analysis on product reviews.",
                   tags=["Sentiment Analysis"])
        self.assessor.assess(p)
        assert p.difficulty_level == "L1"

    def test_rl_tag_is_l3(self):
        p = _paper("We study policy gradient methods.", tags=["Reinforcement Learning"])
        self.assessor.assess(p)
        assert p.difficulty_level == "L3"

    def test_returns_paper(self, sample_paper: Paper):
        result = self.assessor.assess(sample_paper)
        assert result is sample_paper
