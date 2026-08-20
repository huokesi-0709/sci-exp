from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from .schemas import ProtocolChunk


def prepare_protocols(
    registry: Iterable[dict[str, Any]],
    *,
    registry_directory: Path,
    target_characters: int = 600,
    overlap_characters: int = 80,
) -> list[ProtocolChunk]:
    chunks: list[ProtocolChunk] = []
    for source in registry:
        source_id = str(source["source_id"]).strip()
        source_path = Path(str(source["file"]))
        if not source_path.is_absolute():
            source_path = registry_directory / source_path
        text = extract_text(source_path)
        source_chunks = chunk_protocol_text(
            text,
            target_characters=target_characters,
            overlap_characters=overlap_characters,
        )
        for index, chunk_text in enumerate(source_chunks, start=1):
            value = dict(source)
            value.update(
                {
                    "evidence_id": f"{source_id}_{index:04d}",
                    "text": chunk_text,
                    "source_org": source["source_org"],
                }
            )
            value.pop("file", None)
            chunks.append(ProtocolChunk.from_dict(value))
    return chunks


def extract_text(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return path.read_text(encoding="utf-8")
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader  # type: ignore
        except ImportError as exc:
            raise RuntimeError(
                "PDF ingestion requires pypdf; install requirements-research.txt"
            ) from exc
        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    raise ValueError(f"unsupported protocol file type: {path.suffix}")


def chunk_protocol_text(
    text: str,
    *,
    target_characters: int = 600,
    overlap_characters: int = 80,
) -> list[str]:
    if target_characters <= 0:
        raise ValueError("target_characters must be positive")
    if overlap_characters < 0 or overlap_characters >= target_characters:
        raise ValueError("overlap_characters must be in [0, target_characters)")
    normalized = re.sub(r"[ \t]+", " ", text.replace("\r\n", "\n"))
    normalized = re.sub(r"\n{3,}", "\n\n", normalized).strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        maximum_end = min(start + target_characters, len(normalized))
        end = maximum_end
        if maximum_end < len(normalized):
            candidates = [
                normalized.rfind(separator, start + target_characters // 2, maximum_end)
                for separator in ("\n\n", "。", "；", ";", ". ")
            ]
            boundary = max(candidates)
            if boundary > start:
                end = boundary + (2 if normalized[boundary : boundary + 2] == "\n\n" else 1)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap_characters, start + 1)
    return chunks
