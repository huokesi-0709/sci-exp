from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any


USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)
SUPPRESSED_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer"}


class VisibleTextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._suppressed_depth = 0
        self._parts: list[str] = []

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        del attrs
        if tag.lower() in SUPPRESSED_TAGS:
            self._suppressed_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in SUPPRESSED_TAGS and self._suppressed_depth:
            self._suppressed_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._suppressed_depth == 0:
            self._parts.append(data)

    def text(self) -> str:
        lines: list[str] = []
        previous = ""
        for part in self._parts:
            for raw_line in part.splitlines():
                line = re.sub(r"\s+", " ", raw_line).strip()
                if not line or line == previous:
                    continue
                lines.append(line)
                previous = line
        return "\n".join(lines)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError as exc:
                raise ValueError(f"{path}:{line_number}: invalid JSON") from exc
    return rows


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def detect_html_encoding(data: bytes, content_type: str) -> str:
    header_match = re.search(r"charset=([\w-]+)", content_type, flags=re.I)
    if header_match:
        declared = header_match.group(1)
        if declared.lower().replace("_", "-") in {
            "iso-8859-1",
            "latin-1",
            "latin1",
        }:
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                return declared
            return "utf-8"
        return declared
    head = data[:4096]
    meta_match = re.search(br"charset=[\"']?\s*([\w-]+)", head, flags=re.I)
    if meta_match:
        return meta_match.group(1).decode("ascii", errors="ignore")
    return "utf-8"


def extract_html_text(
    data: bytes,
    *,
    content_type: str = "",
    start_marker: str = "",
    end_marker: str = "",
) -> str:
    encoding = detect_html_encoding(data, content_type)
    try:
        html = data.decode(encoding, errors="replace")
    except LookupError:
        html = data.decode("utf-8", errors="replace")
    parser = VisibleTextExtractor()
    parser.feed(html)
    text = parser.text()
    if start_marker:
        position = text.find(start_marker)
        if position < 0:
            preview = text[:500].replace("\n", " | ")
            raise ValueError(
                f"content_start_marker not found: {start_marker}; preview={preview}"
            )
        text = text[position:]
    if end_marker:
        position = text.find(end_marker)
        if position >= 0:
            text = text[:position]
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) < 300:
        raise ValueError("extracted HTML text is unexpectedly short")
    return text


def metadata_header(source: dict[str, Any], final_url: str) -> str:
    fields = [
        ("标题", source.get("title", "")),
        ("来源机构", source.get("source_org", "")),
        ("来源页面", source.get("source_url", "")),
        ("实际下载地址", final_url),
        ("版本", source.get("version", "")),
        ("生效日期", source.get("effective_date", "")),
        ("内容状态", source.get("content_review_status", "")),
    ]
    lines = ["# 本地研究副本元数据"]
    lines.extend(f"{name}：{value}" for name, value in fields)
    lines.append("# 正文")
    return "\n".join(lines)


def fetch(url: str, *, timeout: int) -> tuple[bytes, str, str]:
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "application/pdf;q=0.8,*/*;q=0.7"
            ),
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
            "Accept-Encoding": "identity",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        data = response.read()
        final_url = response.geturl()
        content_type = response.headers.get("Content-Type", "")
    if data.startswith(b"\x1f\x8b"):
        data = gzip.decompress(data)
    return data, final_url, content_type


def materialize_source(
    source: dict[str, Any],
    *,
    registry_directory: Path,
    timeout: int,
) -> dict[str, Any]:
    source_id = str(source["source_id"])
    relative_path = Path(str(source["file"]))
    if relative_path.is_absolute():
        raise ValueError(f"{source_id}: file must be relative to registry")
    destination = (registry_directory / relative_path).resolve()
    registry_root = registry_directory.resolve()
    if registry_root not in destination.parents:
        raise ValueError(f"{source_id}: file escapes registry directory")

    if destination.exists():
        actual_sha256 = sha256_file(destination)
        expected_sha256 = str(source.get("file_sha256", "")).strip()
        if expected_sha256 and actual_sha256 != expected_sha256:
            raise ValueError(
                f"{source_id}: existing file hash mismatch: "
                f"expected={expected_sha256}, actual={actual_sha256}"
            )
        return {
            "source_id": source_id,
            "status": "existing_verified",
            "path": str(destination),
            "bytes": destination.stat().st_size,
            "sha256": actual_sha256,
        }

    url = str(source.get("download_url") or source["source_url"])
    data, final_url, content_type = fetch(url, timeout=timeout)
    retrieval_mode = str(source["retrieval_mode"])

    if retrieval_mode == "pdf":
        if not data.startswith(b"%PDF"):
            raise ValueError(
                f"{source_id}: expected PDF but received {content_type or 'unknown'}"
            )
        output = data
        extracted_characters = None
    elif retrieval_mode == "html_to_text":
        text = extract_html_text(
            data,
            content_type=content_type,
            start_marker=str(source.get("content_start_marker", "")),
            end_marker=str(source.get("content_end_marker", "")),
        )
        output = (
            metadata_header(source, final_url) + "\n\n" + text + "\n"
        ).encode("utf-8")
        extracted_characters = len(text)
    else:
        raise ValueError(f"{source_id}: unsupported retrieval_mode={retrieval_mode}")

    output_sha256 = sha256_bytes(output)
    expected_sha256 = str(source.get("file_sha256", "")).strip()
    if expected_sha256 and output_sha256 != expected_sha256:
        raise ValueError(
            f"{source_id}: downloaded file hash mismatch: "
            f"expected={expected_sha256}, actual={output_sha256}"
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.write_bytes(output)
    temporary.replace(destination)
    return {
        "source_id": source_id,
        "status": "downloaded",
        "source_url": source.get("source_url", ""),
        "download_url": url,
        "final_url": final_url,
        "content_type": content_type,
        "retrieval_mode": retrieval_mode,
        "path": str(destination),
        "bytes": len(output),
        "sha256": output_sha256,
        "extracted_characters": extracted_characters,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="下载登记过的权威协议源，并生成可复现哈希报告。"
    )
    parser.add_argument("--registry", required=True)
    parser.add_argument("--report", required=True)
    parser.add_argument("--timeout", type=int, default=60)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    registry_path = Path(args.registry).resolve()
    report_path = Path(args.report).resolve()
    sources = read_jsonl(registry_path)
    source_ids = [str(source.get("source_id", "")) for source in sources]
    if len(source_ids) != len(set(source_ids)):
        raise ValueError("duplicate source_id in registry")

    results: list[dict[str, Any]] = []
    failures: list[dict[str, str]] = []
    for source in sources:
        try:
            result = materialize_source(
                source,
                registry_directory=registry_path.parent,
                timeout=args.timeout,
            )
            results.append(result)
            print(
                json.dumps(
                    {
                        "source_id": result["source_id"],
                        "status": result["status"],
                        "bytes": result["bytes"],
                    },
                    ensure_ascii=False,
                )
            )
        except (OSError, ValueError, urllib.error.URLError) as exc:
            failure = {
                "source_id": str(source.get("source_id", "")),
                "error": f"{type(exc).__name__}: {exc}",
            }
            failures.append(failure)
            print(json.dumps(failure, ensure_ascii=False), file=sys.stderr)

    report = {
        "schema_version": "1.0",
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "registry": {
            "path": str(registry_path),
            "sha256": sha256_file(registry_path),
            "rows": len(sources),
        },
        "policy": {
            "formal_knowledge_base_eligible": False,
            "reason": "all sources remain draft until content, version, and license review",
            "existing_files_are_not_overwritten": True,
        },
        "results": results,
        "failures": failures,
    }
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
