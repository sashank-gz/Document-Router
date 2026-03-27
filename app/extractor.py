import gc
import logging
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from . import config

try:
    from docling.datamodel.pipeline_options import RapidOcrOptions
except ImportError:
    try:
        # Fallback for some Docling versions
        from docling.models.ocr_options import RapidOcrOptions
    except ImportError:
        RapidOcrOptions = None

try:
    from docling.datamodel.pipeline_options import EasyOcrOptions
except ImportError:
    try:
        from docling.models.ocr_options import EasyOcrOptions
    except ImportError:
        EasyOcrOptions = None

logger = logging.getLogger(__name__)

# File-size threshold for memory warning (50 MB)
_LARGE_FILE_THRESHOLD_BYTES = 50 * 1024 * 1024


def _save_exports(doc, base_path: Path, suffix: str = "") -> None:
    """Persist Docling exports (MD/JSON/HTML) based on config flags.

    Parameters
    ----------
    doc : Docling document object with export methods.
    base_path : Path to the source PDF (used to derive output filenames).
    suffix : Optional suffix appended to the stem (e.g. "_handwritten").
    """
    import json

    stem = f"{base_path.stem}{suffix}"
    parent = base_path.parent

    if config.DOCLING_SAVE_MD:
        (parent / f"{stem}.md").write_text(doc.export_to_markdown(), encoding="utf-8")
    if config.DOCLING_SAVE_JSON:
        (parent / f"{stem}.json").write_text(
            json.dumps(doc.export_to_dict(), indent=2), encoding="utf-8"
        )
    if config.DOCLING_SAVE_HTML:
        (parent / f"{stem}.html").write_text(doc.export_to_html(), encoding="utf-8")


class AdvancedDoclingExtractor:
    """Production-grade Document Extractor utilizing customized local OCR and table parsing."""

    def __init__(self):
        # Configure local pipeline options exclusively
        self.pipeline_options = PdfPipelineOptions()
        self.pipeline_options.do_ocr = True
        self.pipeline_options.do_table_structure = True

        if RapidOcrOptions:
            self.pipeline_options.ocr_options = RapidOcrOptions()

        self.doc_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(pipeline_options=self.pipeline_options)
            }
        )

    def extract(self, source: Path | str) -> str:
        """Runs the intensive Docling pipeline safely and emits Markdown."""
        try:
            doc = self.doc_converter.convert(str(source)).document
            md_text = doc.export_to_markdown()
            _save_exports(doc, Path(source))
            return md_text
        except Exception as exc:
            source_name = Path(source).name if isinstance(source, Path | str) else str(source)
            logger.exception("Unable to extract text natively from file: %s", source)
            raise RuntimeError(f"Failed to read document natively: {source_name}") from exc


class HandwrittenDoclingExtractor:
    """Specialized extractor for handwritten / scanned PDFs using EasyOCR backend.

    Key differences from AdvancedDoclingExtractor:
      - Uses EasyOCR (deep-learning model) instead of RapidOCR — better at
        recognizing irregular, cursive, and hand-printed characters.
      - Sets ``force_ocr=True`` so OCR runs even when Docling detects a thin
        digital text layer (common in scanned handwriting overlays).
      - Includes a file-size guard and explicit ``gc.collect()`` to keep memory
        usage under control for large multi-page scans.
    """

    def __init__(self, languages: list[str] | None = None):
        if EasyOcrOptions is None:
            raise ImportError(
                "EasyOcrOptions not found. Install the easyocr extra: "
                "pip install 'docling[easyocr]'"
            )

        self.pipeline_options = PdfPipelineOptions()
        self.pipeline_options.do_ocr = True
        self.pipeline_options.do_table_structure = True

        # Force OCR even when a digital text layer exists — handwritten content
        # is often an image overlay on top of a near-empty text layer.
        self.pipeline_options.force_ocr = True

        # Configure EasyOCR backend
        self.pipeline_options.ocr_options = EasyOcrOptions(
            lang=languages or ["en"],
        )

        self.doc_converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=self.pipeline_options,
                )
            }
        )

    def extract(self, source: Path | str) -> str:
        """Convert a handwritten/scanned PDF to Markdown via EasyOCR.

        Returns
        -------
        str
            Markdown text preserving layout structure (tables, headers, etc.).

        Raises
        ------
        RuntimeError
            If conversion fails for any reason.
        """
        source = Path(source)

        # ── Memory guard ────────────────────────────────────────────────
        try:
            file_size = source.stat().st_size
            if file_size > _LARGE_FILE_THRESHOLD_BYTES:
                logger.warning(
                    "Large file detected (%d MB). EasyOCR may consume "
                    "significant memory. Consider splitting the PDF first.",
                    file_size // (1024 * 1024),
                )
        except OSError:
            pass  # File may be a URL or virtual path — skip the check.

        try:
            doc = self.doc_converter.convert(str(source)).document
            md_text = doc.export_to_markdown()
            _save_exports(doc, source, suffix="_handwritten")
            return md_text
        except Exception as exc:
            logger.exception("Handwritten extraction failed for file: %s", source.name)
            raise RuntimeError(f"Handwritten extraction failed: {source.name}") from exc
        finally:
            # Free heavy EasyOCR / PyTorch tensors promptly
            gc.collect()


# ── Convenience function (singleton pattern) ────────────────────────────
_handwritten_extractor: HandwrittenDoclingExtractor | None = None


def extract_handwriting_from_pdf(
    file_path: Path | str,
    languages: list[str] | None = None,
) -> str:
    """Extract text from a handwritten/scanned PDF and return Markdown.

    Parameters
    ----------
    file_path : Path | str
        Path to the PDF file.
    languages : list[str] | None
        Language codes for EasyOCR (default ``["en"]``).

    Returns
    -------
    str
        Markdown-formatted text with tables, headers, etc. preserved.
    """
    global _handwritten_extractor
    if _handwritten_extractor is None:
        _handwritten_extractor = HandwrittenDoclingExtractor(languages=languages)
    return _handwritten_extractor.extract(file_path)
