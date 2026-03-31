"""Unit tests for the 3-tier document classifier."""

from unittest.mock import patch

from app.classifier import (
    ClassificationResult,
    _classify_by_filename,
    _classify_by_keywords,
    classify_document,
)
from app.document_types import DocumentType, Pipeline


class TestTier1Filename:
    """Tests for _classify_by_filename."""

    def test_matches_loss_run(self):
        result = _classify_by_filename("company_loss_run_2024.pdf")
        assert result is not None
        assert result.document_type == DocumentType["LOSS_RUN"]
        assert result.tier == "filename"

    def test_matches_acord(self):
        result = _classify_by_filename("acord_125_form.pdf")
        assert result is not None
        assert result.document_type == DocumentType["ACORD"]

    def test_no_match_returns_none(self):
        result = _classify_by_filename("random_document.pdf")
        assert result is None

    def test_empty_filename(self):
        result = _classify_by_filename("")
        assert result is None

    def test_none_filename(self):
        result = _classify_by_filename(None)
        assert result is None

    def test_case_insensitive(self):
        result = _classify_by_filename("LOSS_RUN_REPORT.PDF")
        assert result is not None
        assert result.document_type == DocumentType["LOSS_RUN"]


class TestTier2Keywords:
    """Tests for _classify_by_keywords."""

    def test_matches_known_keyword(self):
        """Keyword hints should match when present in text."""
        with patch.dict("app.classifier.KEYWORD_HINTS", {"LOSS_RUN": ["loss run"]}, clear=True):
            result = _classify_by_keywords("This is a loss run report with claim number 12345")

        assert result is not None
        assert result.tier == "keyword"

    def test_no_match_returns_none(self):
        result = _classify_by_keywords("Buy milk and eggs from the store")
        assert result is None

    def test_empty_text(self):
        result = _classify_by_keywords("")
        assert result is None

    def test_none_text(self):
        result = _classify_by_keywords(None)
        assert result is None

    def test_normalizes_whitespace(self):
        """Multi-line text should be collapsed for matching."""
        with patch.dict(
            "app.classifier.KEYWORD_HINTS",
            {"LOSS_RUN": ["loss run"]},
            clear=True,
        ):
            result = _classify_by_keywords("loss\n   run\n  report")

        assert result is not None
        assert result.tier == "keyword"


class TestClassifyDocument:
    """Tests for the full classify_document orchestrator."""

    def test_tier2_match_returns_result(self):
        """When Tier 2 matches, should return that result."""
        with patch("app.classifier._classify_by_keywords") as mock_kw:
            mock_kw.return_value = ClassificationResult(
                document_type=DocumentType["LOSS_RUN"],
                pipeline=Pipeline.OCR,
                tier="keyword",
            )
            with patch("app.classifier._classify_by_filename", return_value=None):
                result, debug = classify_document("random.pdf", "fake text")
                assert result.document_type == DocumentType["LOSS_RUN"]
                assert result.tier == "keyword"

    def test_tier1_and_tier2_agree(self):
        """When both tiers match the same type, tier should be 'both'."""
        loss_run_type = DocumentType["LOSS_RUN"]
        with patch("app.classifier._classify_by_filename") as mock_fn:
            mock_fn.return_value = ClassificationResult(
                document_type=loss_run_type,
                pipeline=Pipeline.OCR,
                tier="filename",
            )
            with patch("app.classifier._classify_by_keywords") as mock_kw:
                mock_kw.return_value = ClassificationResult(
                    document_type=loss_run_type,
                    pipeline=Pipeline.OCR,
                    tier="keyword",
                )
                result, debug = classify_document("loss_run.pdf", "loss run report")
                assert result.tier == "both"

    def test_tier1_and_tier2_conflict_falls_to_unknown_without_llm(self):
        """When Tier 1 and Tier 2 disagree and no LLM text is available, classifier should fall back to UNKNOWN."""
        with patch("app.classifier._classify_by_filename") as mock_fn:
            mock_fn.return_value = ClassificationResult(
                document_type=DocumentType["LOSS_RUN"],
                pipeline=Pipeline.OCR,
                tier="filename",
            )
            with patch("app.classifier._classify_by_keywords") as mock_kw:
                mock_kw.return_value = ClassificationResult(
                    document_type=DocumentType["ACORD"],
                    pipeline=Pipeline.OCR,
                    tier="keyword",
                )
                # No LLM text provided -> should fall through to UNKNOWN (tier 'none')
                result, debug = classify_document("loss_run.pdf", "acord form")
                assert result.document_type == DocumentType["UNKNOWN"]
                assert result.tier == "none"

    def test_no_match_falls_to_manual(self):
        """When nothing matches and no LLM text, should return UNKNOWN/MANUAL."""
        with patch("app.classifier._classify_by_filename", return_value=None):
            with patch("app.classifier._classify_by_keywords", return_value=None):
                result, debug = classify_document("random.pdf", "no keywords here")
                assert result.document_type == DocumentType["UNKNOWN"]
                assert result.pipeline == Pipeline.MANUAL
                assert result.confidence == 0.0

    def test_tier1_alone_falls_back_to_filename(self):
        """When Tier 2 is empty and Tier 3 has no usable text, fallback should use Tier 1."""
        with patch("app.classifier._classify_by_filename") as mock_fn:
            mock_fn.return_value = ClassificationResult(
                document_type=DocumentType["LOSS_RUN"],
                pipeline=Pipeline.OCR,
                tier="filename",
            )
            with patch("app.classifier._classify_by_keywords", return_value=None):
                result, debug = classify_document("loss_run.pdf", "")
                assert result.document_type == DocumentType["LOSS_RUN"]
                assert result.pipeline == Pipeline.OCR
                assert result.tier == "filename"

    def test_short_llm_text_skips_tier3_and_uses_tier1(self):
        """Very short metadata should not invoke Tier 3; fallback remains deterministic."""
        with patch("app.classifier._classify_by_filename") as mock_fn:
            mock_fn.return_value = ClassificationResult(
                document_type=DocumentType["LOSS_RUN"],
                pipeline=Pipeline.OCR,
                tier="filename",
            )
            with patch("app.classifier._classify_by_keywords", return_value=None):
                with patch("app.config.LLM_MIN_TEXT_CHARS", 180):
                    with patch("app.llm_classifier.classify_with_llm") as mock_llm:
                        result, debug = classify_document(
                            "loss_run.pdf",
                            "",
                            llm_text="# Email: subject only\nFrom: sender@example.com",
                        )
                        assert result.document_type == DocumentType["LOSS_RUN"]
                        assert result.pipeline == Pipeline.OCR
                        assert result.tier == "filename"
                        mock_llm.assert_not_called()

    def test_tier1_only_long_text_prefers_filename_without_llm(self):
        """Tier 1-only flows should stay deterministic and skip Tier 3."""
        with patch("app.classifier._classify_by_filename") as mock_fn:
            mock_fn.return_value = ClassificationResult(
                document_type=DocumentType["LOSS_RUN"],
                pipeline=Pipeline.OCR,
                tier="filename",
            )
            with patch("app.classifier._classify_by_keywords", return_value=None):
                with patch("app.llm_classifier.classify_with_llm") as mock_llm:
                    result, debug = classify_document(
                        "loss_run.pdf",
                        "",
                        llm_text="This is a long body text " * 30,
                    )
                    assert result.document_type == DocumentType["LOSS_RUN"]
                    assert result.pipeline == Pipeline.OCR
                    assert result.tier == "filename"
                    mock_llm.assert_not_called()
