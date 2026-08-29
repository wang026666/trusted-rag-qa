from __future__ import annotations

import hashlib
import re
from pathlib import Path


SUPPORTED_SUFFIXES = {".doc", ".docx", ".pdf", ".xls", ".xlsx", ".txt", ".csv", ".html"}


def sha256_file(path: Path, block_size: int = 1024 * 1024) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            block = f.read(block_size)
            if not block:
                break
            digest.update(block)
    return digest.hexdigest()


def parse_attachment_name(path: Path) -> dict:
    name = path.name
    suffix = path.suffix.lower().lstrip(".")
    match = re.match(r"^(?P<num>\d+)_([^_]+)_(.+)$", name)
    if match:
        number = match.group("num")
        rest = name[len(number) + 1 :]
        title, file_label = rest.rsplit("_", 1)
        doc_id = f"nfra_{number}"
    else:
        number = ""
        title = path.stem
        file_label = path.name
        doc_id = path.stem
    return {
        "doc_id": doc_id,
        "source_number": number,
        "title": title,
        "file_label": file_label,
        "file_type": suffix,
    }


def classify_file(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".xls", ".xlsx", ".csv"}:
        return "table"
    if suffix in {".doc", ".docx", ".pdf", ".txt", ".html"}:
        return "text"
    return "unknown"


def build_manifest(attachments_dir: Path) -> list[dict]:
    records: list[dict] = []
    for path in sorted(attachments_dir.iterdir(), key=lambda p: p.name):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        parsed = parse_attachment_name(path)
        records.append(
            {
                **parsed,
                "local_path": str(path.resolve()),
                "relative_path": str(path.relative_to(attachments_dir.parent)),
                "file_size": path.stat().st_size,
                "sha256": sha256_file(path),
                "source_url": "",
                "attachment_url": "",
                "category": classify_file(path),
            }
        )
    return records
