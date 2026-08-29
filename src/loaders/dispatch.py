from __future__ import annotations

from pathlib import Path

from src.loaders.docx_loader import load_doc, load_docx
from src.loaders.excel_loader import load_excel
from src.loaders.pdf_loader import load_pdf
from src.loaders.text_loader import load_txt


def load_document(path: Path, metadata: dict) -> list[dict]:
    suffix = path.suffix.lower()
    if suffix == ".txt":
        return load_txt(path, metadata)
    if suffix == ".docx":
        return load_docx(path, metadata)
    if suffix == ".doc":
        return load_doc(path, metadata)
    if suffix == ".pdf":
        return load_pdf(path, metadata)
    if suffix in {".xls", ".xlsx", ".csv"}:
        return load_excel(path, metadata)
    return []
