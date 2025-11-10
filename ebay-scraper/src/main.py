import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from extractors.ebay_parser import EbayParser
from extractors.proxy_handler import ProxyManager
from outputs.json_exporter import JSONExporter
from outputs.csv_exporter import CSVExporter
from outputs.xml_exporter import XMLExporter
from outputs.excel_exporter import ExcelExporter

EXPORTERS = {
    "json": JSONExporter,
    "csv": CSVExporter,
    "xml": XMLExporter,
    "excel": ExcelExporter,
    "xlsx": ExcelExporter,
}

def load_json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)

def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="eBay Scraper — extract structured listing data from eBay search or category pages."
    )
    parser.add_argument(
        "--config",
        type=str,
        default=str(Path(__file__).parent / "config" / "settings.example.json"),
        help="Path to a settings JSON file.",
    )
    parser.add_argument(
        "--input",
        type=str,
        default=str(Path(__file__).parents[1] / "data" / "sample_input.json"),
        help="Path to input JSON with 'urls' or 'keywords'.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=str(Path(__file__).parents[1] / "data"),
        help="Directory to store outputs.",
    )
    parser.add_argument(
        "--formats",
        type=str,
        default="json,csv",
        help="Comma-separated list of output formats (json,csv,xml,excel).",
    )
    parser.add_argument(
        "--max-items",
        type=int,
        default=None,
        help="Override max items to scrape.",
    )
    parser.add_argument(
        "--proxy",
        type=str,
        default=None,
        help="Proxy URL (overrides config), e.g. http://user:pass@host:port",
    )
    return parser.parse_args()

def build_export_basename(output_dir: Path) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    return output_dir / f"ebay_scrape_{ts}"

def main() -> None:
    args = parse_args()
    config_path = Path(args.config)
    input_path = Path(args.input)
    output_dir = Path(args.output_dir)
    ensure_dir(output_dir)

    if not config_path.exists():
        print(f"[ERROR] Config not found: {config_path}", file=sys.stderr)
        sys.exit(1)
    if not input_path.exists():
        print(f"[ERROR] Input not found: {input_path}", file=sys.stderr)
        sys.exit(1)

    settings = load_json(config_path)
    inputs = load_json(input_path)

    # Override settings from CLI when provided
    if args.max_items is not None:
        settings.setdefault("input", {})
        settings["input"]["maxItems"] = args.max_items

    formats = [f.strip().lower() for f in args.formats.split(",") if f.strip()]
    base = build_export_basename(output_dir)

    # Proxy setup
    proxy_manager = ProxyManager(
        proxies=[args.proxy] if args.proxy else settings.get("proxies", {}).get("pool", []),
        single_proxy=settings.get("proxies", {}).get("single"),
        rotate=str(settings.get("proxies", {}).get("rotate", True)).lower() == "true",
    )

    # Initialize parser
    parser = EbayParser(
        region=settings.get("input", {}).get("region", "US"),
        max_items=settings.get("input", {}).get("maxItems", 200),
        delay=settings.get("input", {}).get("delaySeconds", 0.5),
        proxy_manager=proxy_manager,
        user_agent=settings.get("http", {}).get(
            "userAgent",
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36",
        ),
        timeout=settings.get("http", {}).get("timeoutSeconds", 20),
        follow_item_page=bool(settings.get("input", {}).get("followItemPage", False)),
    )

    urls: List[str] = inputs.get("urls", [])
    keywords: List[str] = inputs.get("keywords", [])

    if not urls and not keywords:
        print("[ERROR] Provide at least one URL or keyword in input JSON.", file=sys.stderr)
        sys.exit(1)

    try:
        data = parser.run(urls=urls, keywords=keywords)
    except Exception as e:
        print(f"[FATAL] Scrape failed: {e}", file=sys.stderr)
        sys.exit(2)

    if not data:
        print("[WARN] No data extracted.")
        sys.exit(0)

    # Export
    for fmt in formats:
        exporter_cls = EXPORTERS.get(fmt)
        if not exporter_cls:
            print(f"[WARN] Unknown format '{fmt}', skipping.")
            continue
        exporter = exporter_cls()
        out_path = base.with_suffix(
            ".xlsx" if fmt in ("excel", "xlsx") else f".{fmt}"
        )
        try:
            exporter.export(data, out_path)
            print(f"[OK] Wrote {fmt.upper()} -> {out_path}")
        except Exception as e:
            print(f"[ERROR] Failed to write {fmt.upper()}: {e}", file=sys.stderr)

    # Also persist a canonical JSON for pipeline use
    json_path = base.with_suffix(".json")
    try:
        JSONExporter(indent=2).export(data, json_path)
        print(f"[OK] Wrote JSON snapshot -> {json_path}")
    except Exception as e:
        print(f"[ERROR] Failed to write JSON snapshot: {e}", file=sys.stderr)

if __name__ == "__main__":
    main()