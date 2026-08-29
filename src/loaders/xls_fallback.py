from __future__ import annotations

import re
import struct
from pathlib import Path

from src.loaders.text_loader import make_chunk


FREE_SECTOR = 0xFFFFFFFF
END_OF_CHAIN = 0xFFFFFFFE


class CompoundFile:
    """Minimal OLE reader for old .xls text fallback."""

    def __init__(self, path: Path):
        self.data = path.read_bytes()
        header = self.data[:512]
        if header[:8] != b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1":
            raise RuntimeError("not an OLE compound document")
        self.sector_size = 1 << struct.unpack_from("<H", header, 30)[0]
        self.first_dir_sector = struct.unpack_from("<I", header, 48)[0]
        self.num_fat_sectors = struct.unpack_from("<I", header, 44)[0]
        difat = list(struct.unpack_from("<109I", header, 76))
        self.difat = [sid for sid in difat if sid != FREE_SECTOR]
        self.fat: list[int] = []
        for sector_id in self.difat[: self.num_fat_sectors]:
            sector = self.sector(sector_id)
            self.fat.extend(struct.unpack("<%dI" % (self.sector_size // 4), sector))

    def sector(self, sector_id: int) -> bytes:
        offset = (sector_id + 1) * self.sector_size
        return self.data[offset : offset + self.sector_size]

    def chain(self, start_sector: int, max_sectors: int = 20000) -> bytes:
        output = bytearray()
        sector_id = start_sector
        seen: set[int] = set()
        while (
            sector_id not in (END_OF_CHAIN, FREE_SECTOR)
            and sector_id < len(self.fat)
            and sector_id not in seen
            and len(seen) < max_sectors
        ):
            seen.add(sector_id)
            output.extend(self.sector(sector_id))
            sector_id = self.fat[sector_id]
        return bytes(output)

    def directory_entries(self) -> list[dict]:
        directory = self.chain(self.first_dir_sector)
        entries: list[dict] = []
        for offset in range(0, len(directory), 128):
            entry = directory[offset : offset + 128]
            if len(entry) < 128:
                break
            name_len = struct.unpack_from("<H", entry, 64)[0]
            if name_len < 2:
                continue
            name = entry[: name_len - 2].decode("utf-16le", errors="ignore")
            entries.append(
                {
                    "name": name,
                    "type": entry[66],
                    "start_sector": struct.unpack_from("<I", entry, 116)[0],
                    "size": struct.unpack_from("<I", entry, 120)[0],
                }
            )
        return entries

    def open_stream(self, names: set[str]) -> bytes:
        for entry in self.directory_entries():
            if entry["name"] in names:
                return self.chain(entry["start_sector"])[: entry["size"]]
        raise RuntimeError(f"stream not found: {names}")


def _iter_biff_records(workbook: bytes):
    position = 0
    while position + 4 <= len(workbook):
        opcode, length = struct.unpack_from("<HH", workbook, position)
        data = workbook[position + 4 : position + 4 + length]
        yield opcode, data
        position += 4 + length


def _read_xl_unicode_string(blob: bytes, offset: int) -> tuple[str, int]:
    if offset + 3 > len(blob):
        return "", len(blob)
    char_count = struct.unpack_from("<H", blob, offset)[0]
    flags = blob[offset + 2]
    offset += 3
    if flags & 0x08:
        offset += 2
    if flags & 0x04:
        offset += 4
    if flags & 0x01:
        raw = blob[offset : offset + char_count * 2]
        return raw.decode("utf-16le", errors="ignore"), offset + char_count * 2
    raw = blob[offset : offset + char_count]
    return raw.decode("latin1", errors="ignore"), offset + char_count


def extract_xls_strings(path: Path, max_strings: int = 5000) -> list[str]:
    workbook = CompoundFile(path).open_stream({"Workbook", "Book"})
    records = list(_iter_biff_records(workbook))
    strings: list[str] = []

    for idx, (opcode, data) in enumerate(records):
        if opcode == 0x00FC:
            blob = bytearray(data)
            cursor = idx + 1
            while cursor < len(records) and records[cursor][0] == 0x003C:
                blob.extend(records[cursor][1])
                cursor += 1
            offset = 8
            while offset < len(blob) and len(strings) < max_strings:
                text, offset = _read_xl_unicode_string(bytes(blob), offset)
                if text:
                    strings.append(text)
        elif opcode == 0x0204 and len(data) > 8:
            text, _ = _read_xl_unicode_string(data, 6)
            if text:
                strings.append(text)

    cleaned: list[str] = []
    seen: set[str] = set()
    for item in strings:
        text = re.sub(r"\s+", " ", item).strip()
        if not text or text in seen:
            continue
        if re.search(r"[\u4e00-\u9fffA-Za-z0-9]", text):
            cleaned.append(text)
            seen.add(text)
    return cleaned


def load_xls_text_fallback(path: Path, metadata: dict) -> list[dict]:
    strings = extract_xls_strings(path)
    chunks: list[dict] = []
    window = 24
    for idx in range(0, len(strings), window):
        part = "；".join(strings[idx : idx + window])
        if not part:
            continue
        chunks.append(
            make_chunk(
                path,
                metadata,
                f"文件：{metadata.get('title', path.stem)}；旧版Excel文本抽取：{part}",
                f"{metadata.get('doc_id', path.stem)}::xls_text::{idx // window + 1}",
                section="旧版Excel文本抽取",
                extra={"sheet_name": "xls_text_fallback"},
            )
        )
    return chunks
