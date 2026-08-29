from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

from src.loaders.text_loader import make_chunk
from src.preprocess.chunking import normalize_text


def _col_name(index: int) -> str:
    name = ""
    index += 1
    while index:
        index, rem = divmod(index - 1, 26)
        name = chr(65 + rem) + name
    return name


def _format_value(value) -> str:
    if value is None:
        return ""
    text = str(value)
    if text == "nan":
        return ""
    return normalize_text(text)


def _cell_ref(col_idx: int, row_no: int) -> str:
    return f"{_col_name(col_idx)}{row_no}"


def build_cell_chunk(
    path: Path,
    metadata: dict,
    sheet_name: str,
    row_no: int,
    col_idx: int,
    value: str,
    row_context: str = "",
    header_context: str = "",
) -> dict:
    column = _col_name(col_idx)
    cell = _cell_ref(col_idx, row_no)
    text = (
        f"文件：{metadata.get('title', path.stem)}；工作表：{sheet_name}；"
        f"单元格：{cell}；列：{column}；行：{row_no}；值：{value}"
    )
    if row_context:
        text += f"；同行上下文：{row_context}"
    if header_context:
        text += f"；表头上下文：{header_context}"
    return make_chunk(
        path,
        metadata,
        text,
        f"{metadata.get('doc_id', path.stem)}::sheet::{sheet_name}::cell::{cell}",
        section=f"工作表:{sheet_name}",
        extra={
            "sheet_name": sheet_name,
            "row": str(row_no),
            "column": column,
            "cell": cell,
            "value": value,
            "chunk_type": "table_cell",
        },
    )


def _convert_xls_to_xlsx(path: Path) -> Path:
    soffice = shutil.which("soffice")
    if not soffice:
        raise RuntimeError("xlrd is missing and LibreOffice soffice is not available")
    tmpdir = Path(tempfile.mkdtemp(prefix="fintech_rag_xls_"))
    result = subprocess.run(
        [
            soffice,
            "--headless",
            "--convert-to",
            "xlsx",
            "--outdir",
            str(tmpdir),
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(f"LibreOffice failed to convert {path}: {result.stderr}")
    converted = list(tmpdir.glob("*.xlsx"))
    if not converted:
        raise RuntimeError(f"LibreOffice did not produce xlsx for {path}")
    return converted[0]


def load_excel(path: Path, metadata: dict, max_rows_per_sheet: int = 800) -> list[dict]:
    try:
        import pandas as pd
    except ImportError as exc:
        raise RuntimeError("pandas is required to parse Excel files") from exc

    read_path = path
    try:
        engine = "xlrd" if path.suffix.lower() == ".xls" else None
        excel = pd.ExcelFile(read_path, engine=engine)
    except (ImportError, ValueError, OSError) as initial_error:
        if path.suffix.lower() != ".xls":
            raise
        try:
            read_path = _convert_xls_to_xlsx(path)
            excel = pd.ExcelFile(read_path)
        except Exception as conversion_error:
            raise RuntimeError(
                f"无法以结构化方式解析旧版 XLS 文件：{path.name}"
            ) from conversion_error

    chunks: list[dict] = []
    for sheet_name in excel.sheet_names:
        df = pd.read_excel(read_path, sheet_name=sheet_name, header=None, nrows=max_rows_per_sheet)
        recent_rows: list[str] = []
        header_rows: list[str] = []
        for row_idx, row in df.iterrows():
            pairs: list[str] = []
            row_values: list[tuple[int, str]] = []
            for col_idx, value in enumerate(row.tolist()):
                text = _format_value(value)
                if text:
                    pairs.append(f"{_col_name(col_idx)}列={text}")
                    row_values.append((col_idx, text))
            if not pairs:
                continue
            row_no = int(row_idx) + 1
            row_text = "；".join(pairs)
            context = "；".join(recent_rows[-2:])
            text = (
                f"文件：{metadata.get('title', path.stem)}；工作表：{sheet_name}；"
                f"第{row_no}行：{row_text}"
            )
            if context:
                text += f"；上文表头/相邻行：{context}"
            chunks.append(
                make_chunk(
                    path,
                    metadata,
                    text,
                    f"{metadata.get('doc_id', path.stem)}::sheet::{sheet_name}::row::{row_no}",
                    section=f"工作表:{sheet_name}",
                    extra={"sheet_name": sheet_name, "row": str(row_no)},
                )
            )
            header_context = "；".join(header_rows[-3:])
            for col_idx, value in row_values:
                chunks.append(
                    build_cell_chunk(
                        path=path,
                        metadata=metadata,
                        sheet_name=sheet_name,
                        row_no=row_no,
                        col_idx=col_idx,
                        value=value,
                        row_context=row_text,
                        header_context=header_context,
                    )
                )
            if row_no <= 5:
                header_rows.append(row_text)
            recent_rows.append(row_text)
    return chunks
