import logging
from pathlib import Path

from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.datamodel.pipeline_options import PdfPipelineOptions
from docling.datamodel.base_models import InputFormat
from . import config

try:
    from docling.datamodel.pipeline_options import RapidOcrOptions
except ImportError:
    try:
        # Fallback for some Docling versions
        from docling.models.ocr_options import RapidOcrOptions
    except ImportError:
        RapidOcrOptions = None

logger = logging.getLogger(__name__)

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
                InputFormat.PDF: PdfFormatOption(
                    pipeline_options=self.pipeline_options
                )
            }
        )

    def extract(self, source: Path | str) -> str:
        """Runs the intensive Docling pipeline safely and emits Markdown."""
        try:
            doc = self.doc_converter.convert(str(source)).document
            
            md_text = doc.export_to_markdown()
            
            base_path = Path(source)
            if config.DOCLING_SAVE_MD:
                (base_path.parent / f"{base_path.stem}.md").write_text(md_text, encoding="utf-8")
                
            if config.DOCLING_SAVE_JSON:
                import json
                (base_path.parent / f"{base_path.stem}.json").write_text(json.dumps(doc.export_to_dict()), encoding="utf-8")
                
            if config.DOCLING_SAVE_HTML:
                (base_path.parent / f"{base_path.stem}.html").write_text(doc.export_to_html(), encoding="utf-8")
                
            return md_text
        except Exception as exc:
            source_name = Path(source).name if isinstance(source, (Path, str)) else str(source)
            logger.exception("Unable to extract text natively from file: %s", source)
            raise RuntimeError(f"Failed to read document natively: {source_name}") from exc
