from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="按PDF页扫描协议关键词。")
    parser.add_argument("--pdf", required=True)
    parser.add_argument("--term", action="append", required=True)
    parser.add_argument("--show-page", action="append", type=int, default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise RuntimeError("需要安装pypdf") from exc

    path = Path(args.pdf).resolve()
    pages = [
        (index, page.extract_text() or "")
        for index, page in enumerate(PdfReader(str(path)).pages, start=1)
    ]
    result = {
        "file": str(path),
        "pages": len(pages),
        "hits": {
            term: [
                page_number
                for page_number, text in pages
                if term.casefold() in text.casefold()
            ]
            for term in args.term
        },
        "page_text": {
            str(page_number): text[:5000]
            for page_number, text in pages
            if page_number in set(args.show_page)
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
