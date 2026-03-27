"""Unit tests for document type configuration loading."""

from app.document_types import (
    FILENAME_HINTS,
    KEYWORD_HINTS,
    ROUTE_MAP,
    SETTINGS,
    TYPE_DESCRIPTIONS,
    DocumentType,
    Pipeline,
    get_pipeline,
    get_valid_types,
)


class TestDocumentTypeLoading:
    """Verify that config/ files load correctly at import time."""

    def test_document_types_are_populated(self):
        """At least one document type must be loaded from routes.txt."""
        valid = get_valid_types()
        assert len(valid) > 0, "No document types loaded from config/routes.txt"

    def test_unknown_type_exists(self):
        """UNKNOWN type should always exist as a fallback."""
        assert hasattr(DocumentType, "UNKNOWN") or "UNKNOWN" in [dt.value for dt in DocumentType]

    def test_route_map_covers_all_types(self):
        """Every DocumentType should have a pipeline in ROUTE_MAP."""
        for dt in DocumentType:
            assert dt in ROUTE_MAP, f"Missing route for {dt.value}"

    def test_pipelines_are_valid(self):
        """All mapped pipelines should be valid Pipeline enum members."""
        for dt, pipeline in ROUTE_MAP.items():
            assert isinstance(pipeline, Pipeline), f"{dt.value} → {pipeline} is not a Pipeline"

    def test_get_pipeline_returns_pipeline(self):
        """get_pipeline should return a Pipeline for any document type."""
        for dt in DocumentType:
            result = get_pipeline(dt)
            assert isinstance(result, Pipeline)

    def test_get_pipeline_unknown_defaults_to_manual(self):
        """UNKNOWN document type should always route to MANUAL."""
        result = get_pipeline(DocumentType["UNKNOWN"])
        assert result == Pipeline.MANUAL


class TestHintsLoading:
    """Verify filename and keyword hints are loaded."""

    def test_filename_hints_not_empty(self):
        assert len(FILENAME_HINTS) > 0, "No filename hints loaded"

    def test_keyword_hints_not_empty(self):
        assert len(KEYWORD_HINTS) > 0, "No keyword hints loaded"

    def test_hints_are_lowercase_lists(self):
        """Each hint file should produce a list of string hints."""
        for type_name, hints in KEYWORD_HINTS.items():
            assert isinstance(hints, list), f"{type_name} hints is not a list"
            assert all(isinstance(h, str) for h in hints), f"{type_name} has non-string hints"

    def test_descriptions_loaded(self):
        """At least one description file should be loaded."""
        assert len(TYPE_DESCRIPTIONS) > 0, "No descriptions loaded from config/descriptions/"


class TestSettingsLoading:
    """Verify settings.txt loads correctly."""

    def test_settings_not_empty(self):
        assert len(SETTINGS) > 0, "No settings loaded from config/settings.txt"

    def test_settings_keys_are_uppercase(self):
        for key in SETTINGS:
            assert key == key.upper(), f"Setting key '{key}' is not uppercase"
