"""
Extraction handlers for various file formats using the Strategy pattern.
"""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.document_converter import DocumentConverter, PdfFormatOption

from . import config
from .file_utils import FileCategory

logger = logging.getLogger(__name__)


@dataclass
class ExtractionResult:
    raw_text: str
    markdown: str
    structured_json: dict[str, Any] | None = None
    attachments: list[Path] = field(default_factory=list)


class BaseHandler(ABC):
    @abstractmethod
    def handle(self, file_path: Path) -> ExtractionResult:
        pass

    def _normalize_text(self, text: str) -> str:
        """Normalize whitespace for consistent classification."""
        if not text:
            return ""
        return " ".join(text.split())


class DoclingHandler(BaseHandler):
    """Handler for formats supported by Docling (PDF, DOCX, XLSX)."""

    def __init__(self, input_format: InputFormat):
        self.input_format = input_format
        # Initialize docling converter with requested format
        pipeline_options = PdfPipelineOptions()
        pipeline_options.do_ocr = config.DOCLING_DO_OCR
        pipeline_options.do_table_structure = config.DOCLING_DO_TABLES

        self.converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options)}
        )

    def handle(self, file_path: Path) -> ExtractionResult:
        try:
            result = self.converter.convert(str(file_path))
            doc = result.document

            markdown = doc.export_to_markdown()
            # For classification, we use the raw text content
            raw_text = self._normalize_text(markdown)

            structured_json = doc.export_to_dict()

            return ExtractionResult(
                raw_text=raw_text, markdown=markdown, structured_json=structured_json
            )
        except Exception as e:
            logger.exception(f"Docling conversion failed for {file_path}")
            raise RuntimeError(f"Failed to extract text from {file_path.name}: {str(e)}") from e


class ExcelHandler(BaseHandler):
    """Specialized handler for Excel to meet sheet-naming and row-limit requirements."""

    def handle(self, file_path: Path) -> ExtractionResult:
        # We can use pandas or openpyxl for more control, but docling also handles XLSX.
        # However, to meet the specific requirements (limit rows for classification, sheet names as headers),
        # a custom implementation using openpyxl or pandas might be safer for 'raw_text'.
        import pandas as pd

        try:
            all_sheets = pd.read_excel(file_path, sheet_name=None)
            full_markdown = []
            classification_text = []

            for sheet_name, df in all_sheets.items():
                section_header = f"## Sheet: {sheet_name}"
                full_markdown.append(section_header)
                full_markdown.append(df.to_markdown(index=False))

                # Limit rows for classification (from config)
                limited_df = df.head(config.EXTRACTION_PREVIEW_LIMIT)
                classification_text.append(
                    f"Sheet {sheet_name}: {limited_df.to_string(index=False)}"
                )

            markdown_out = "\n\n".join(full_markdown)
            raw_text_out = self._normalize_text("\n".join(classification_text))

            return ExtractionResult(
                raw_text=raw_text_out,
                markdown=markdown_out,
                structured_json={
                    "sheets": {
                        name: df.to_dict(orient="records") for name, df in all_sheets.items()
                    }
                },
            )
        except Exception as e:
            logger.exception(f"Excel custom extraction failed for {file_path}")
            # Fallback to docling if pandas fails? Or just fail.
            raise RuntimeError(f"Excel extraction failed: {str(e)}") from e


class CSVHandler(BaseHandler):
    def handle(self, file_path: Path) -> ExtractionResult:
        try:
            import pandas as pd

            df = pd.read_csv(file_path)
            markdown = df.to_markdown(index=False)

            # Limit rows for classification (from config)
            raw_text = self._normalize_text(
                df.head(config.EXTRACTION_PREVIEW_LIMIT).to_string(index=False)
            )

            return ExtractionResult(
                raw_text=raw_text, markdown=markdown, structured_json=df.to_dict(orient="records")
            )
        except Exception as e:
            logger.error(f"CSV extraction failed: {e}")
            raise


class JSONHandler(BaseHandler):
    def handle(self, file_path: Path) -> ExtractionResult:
        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)

            pretty_json = json.dumps(data, indent=2)
            markdown = f"```json\n{pretty_json}\n```"
            raw_text = self._normalize_text(pretty_json)

            return ExtractionResult(raw_text=raw_text, markdown=markdown, structured_json=data)
        except Exception as e:
            logger.error(f"JSON extraction failed: {e}")
            raise


class EmailHandler(BaseHandler):
    """Handler for .eml and .msg files."""

    def handle(self, file_path: Path) -> ExtractionResult:
        from .email_utils import parse_eml, parse_msg

        ext = file_path.suffix.lower()
        if ext == ".eml":
            parser = parse_eml
        elif ext == ".msg":
            parser = parse_msg
        else:
            raise ValueError(f"Unsupported email format: {ext}")

        # Extract metadata and attachments
        metadata: dict[str, Any] | None = None
        attachments: list[Path] = []
        try:
            metadata, attachments = parser(file_path, file_path.parent)

            subject = (
                metadata.get("subject", "(no subject)")
                if isinstance(metadata, dict)
                else "(no subject)"
            )
            sender = (
                metadata.get("from", "(unknown)") if isinstance(metadata, dict) else "(unknown)"
            )
            body = metadata.get("body", "") if isinstance(metadata, dict) else ""

            # Unified markdown formatting
            md_content = f"# Email: {subject}\n**From:** {sender}\n\n{body}"
            raw_text = self._normalize_text(md_content)

            return ExtractionResult(
                raw_text=raw_text,
                markdown=md_content,
                structured_json=metadata if isinstance(metadata, dict) else {},
                attachments=attachments,
            )
        except Exception:
            logger.exception("Email extraction failed for %s", file_path)
            # Graceful degradation: return what we have (even partial results are better than none)
            safe_metadata = metadata if isinstance(metadata, dict) else {}
            return ExtractionResult(
                raw_text="",
                markdown="",
                structured_json=safe_metadata,
                attachments=attachments,
            )


class ExtractionRegistry:
    """Registry to manage and fetch handlers based on FileCategory."""

    def __init__(self):
        self._handlers: dict[FileCategory, BaseHandler] = {
            FileCategory.PDF: DoclingHandler(InputFormat.PDF),
            FileCategory.DOCUMENT: DoclingHandler(InputFormat.DOCX),
            FileCategory.SPREADSHEET: ExcelHandler(),  # Using custom excel handler
            FileCategory.DATA: CSVHandler(),  # Default to CSV, JSON handled by switch or registry
            FileCategory.EMAIL: EmailHandler(),
        }

    def get_handler(self, category: FileCategory, file_path: Path) -> BaseHandler:
        # Special logic for DATA category which contains both CSV and JSON
        if category == FileCategory.DATA:
            if file_path.suffix.lower() == ".json":
                return JSONHandler()
            return CSVHandler()

        handler = self._handlers.get(category)
        if not handler:
            raise ValueError(f"No handler registered for category: {category}")
        return handler


# Global registry instance
registry = ExtractionRegistry()


def extract_content(file_path: Path, category: FileCategory) -> ExtractionResult:
    """Unified entry point for extraction."""
    handler = registry.get_handler(category, file_path)
    return handler.handle(file_path)
