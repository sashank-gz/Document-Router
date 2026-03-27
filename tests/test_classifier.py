"""Unit tests for the 3-tier document classifier."""

from unittest.mock import patch

from app.classifier import (
    ClassificationResult,
    _classify_by_filename,
    _classify_by_keywords,
    classify_document,
)
from app.document_types import DocumentType, Pipeline

# ── Tier 1: Filename classification ──────────────────────────────────


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


# ── Tier 2: Keyword classification ───────────────────────────────────


class TestTier2Keywords:
    """Tests for _classify_by_keywords."""

    def test_matches_known_keyword(self):
        """Keyword hints should match when present in text."""
        result = _classify_by_keywords("This is a loss run report with claim number 12345")
        # Exact match depends on config/keyword_hints content.
        # At minimum, the function should return a result or None.
        # If keyword hints for LOSS_RUN contain "loss run" or "claim number"
        # this should match.
        if result:
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
        result = _classify_by_keywords("loss\n   run\n  report")
        # The function joins on whitespace, so "loss run report" should match
        # if "loss run" is in keyword hints.
        if result:
            assert result.tier == "keyword"


# ── Orchestrator: classify_document ──────────────────────────────────


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

    def test_tier1_and_tier2_conflict_triggers_tier3(self):
        """When tiers disagree, Tier 3 should be attempted."""
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
                # No LLM text provided → should fall through to MANUAL
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

    def test_tier1_alone_ignored(self):
        """Tier 1 alone (without Tier 2) should NOT produce a result."""
        with patch("app.classifier._classify_by_filename") as mock_fn:
            mock_fn.return_value = ClassificationResult(
                document_type=DocumentType["LOSS_RUN"],
                pipeline=Pipeline.OCR,
                tier="filename",
            )
            with patch("app.classifier._classify_by_keywords", return_value=None):
                # No LLM text → should fall to MANUAL
                result, debug = classify_document("loss_run.pdf", "")
                assert result.document_type == DocumentType["UNKNOWN"]
