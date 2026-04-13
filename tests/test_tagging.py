"""Tests for PaperTagger."""
from __future__ import annotations

from src.normalization.schema import Paper
from src.tagging.tagger import PaperTagger


def _paper(abstract: str, title: str = "") -> Paper:
    return Paper(id="t1", title=title, abstract=abstract)


class TestPaperTagger:
    def setup_method(self):
        self.tagger = PaperTagger()

    def test_transformer_attention_tag(self):
        p = self.tagger.tag(_paper("We propose a transformer with attention mechanism."))
        assert "Transformers" in p.tags

    def test_llm_tag(self):
        p = self.tagger.tag(_paper("We study large language model alignment."))
        assert "LLMs" in p.tags

    def test_llm_abbreviation(self):
        p = self.tagger.tag(_paper("LLM-based systems are becoming widespread."))
        assert "LLMs" in p.tags

    def test_diffusion_tag(self):
        p = self.tagger.tag(_paper("We use a diffusion model for image synthesis."))
        assert "Diffusion Models" in p.tags

    def test_rl_tag(self):
        p = self.tagger.tag(_paper("We apply reinforcement learning to robotics."))
        assert "RL" in p.tags

    def test_gnn_tag(self):
        p = self.tagger.tag(_paper("Graph neural networks for node classification."))
        assert "GNN" in p.tags

    def test_rag_tag(self):
        p = self.tagger.tag(_paper("Retrieval-augmented generation improves QA."))
        assert "RAG" in p.tags

    def test_existing_tags_preserved(self):
        p = Paper(id="x", abstract="We study transformers.", tags=["NLP"])
        result = self.tagger.tag(p)
        assert "NLP" in result.tags
        assert "Transformers" in result.tags

    def test_no_irrelevant_tags(self):
        p = self.tagger.tag(_paper("We study weather forecasting with CNNs."))
        assert "LLMs" not in p.tags
        assert "RL" not in p.tags
