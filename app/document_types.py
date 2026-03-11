"""
Document type definitions and route mapping.

Single source of truth for all supported document types and which
extraction pipeline each one should be routed to.
"""

from __future__ import annotations

from enum import Enum


class DocumentType(str, Enum):
    """All document types the platform can classify."""

    LOSS_RUN = "LOSS_RUN"
    POLICY = "POLICY"
    ACORD = "ACORD"
    SOI = "SOI"
    SOV = "SOV"
    BINDER = "BINDER"
    QUOTE = "QUOTE"
    UNKNOWN = "UNKNOWN"


class Pipeline(str, Enum):
    """Available extraction pipelines."""

    OCR = "OCR"
    LLM = "LLM"
    MANUAL = "MANUAL"


# Maps each document type to the pipeline that should process it.
# Add new types here — the rest of the app reads from this mapping.
ROUTE_MAP: dict[DocumentType, Pipeline] = {
    DocumentType.LOSS_RUN: Pipeline.OCR,
    DocumentType.ACORD: Pipeline.OCR,
    DocumentType.POLICY: Pipeline.LLM,
    DocumentType.SOI: Pipeline.LLM,
    DocumentType.SOV: Pipeline.LLM,
    DocumentType.BINDER: Pipeline.LLM,
    DocumentType.QUOTE: Pipeline.LLM,
    DocumentType.UNKNOWN: Pipeline.MANUAL,
}


def get_pipeline(document_type: DocumentType) -> Pipeline:
    """Look up the pipeline for a given document type."""
    return ROUTE_MAP.get(document_type, Pipeline.MANUAL)
