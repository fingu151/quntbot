from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable, Sequence

from scripts.ingest_supplemental_research_sources import fetch_source_text, load_sources


DEFAULT_INPUT_PATH = Path("data/supplemental_research_sources_draft.json")
DEFAULT_VERIFIED_OUTPUT_PATH = Path("data/supplemental_research_sources_verified.json")
DEFAULT_REJECTED_OUTPUT_PATH = Path("data/supplemental_research_sources_rejected.json")
MAX_BODY_TEXT_CHARS = 30000

TextFetcher = Callable[[dict[str, Any]], str | None]


def verify_supplemental_research_sources(
    *,
    input_path: Path | str = DEFAULT_INPUT_PATH,
    verified_output_path: Path | str = DEFAULT_VERIFIED_OUTPUT_PATH,
    rejected_output_path: Path | str = DEFAULT_REJECTED_OUTPUT_PATH,
    text_fetcher: TextFetcher = fetch_source_text,
) -> dict[str, Any]:
    sources = load_sources(str(input_path))
    verified: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for source in sources:
        result = _verify_source(source, text_fetcher)
        if result.get("verified"):
            verified.append(result["source"])
        else:
            rejected.append(result)

    _write_json(verified_output_path, verified)
    _write_json(rejected_output_path, rejected)
    return {
        "input_count": len(sources),
        "verified_count": len(verified),
        "rejected_count": len(rejected),
        "verified_output": str(verified_output_path),
        "rejected_output": str(rejected_output_path),
    }


def _verify_source(source: dict[str, Any], text_fetcher: TextFetcher) -> dict[str, Any]:
    ticker = str(source.get("ticker") or "").strip()
    if not ticker:
        return {"verified": False, "reason": "missing_ticker", "source": source}
    try:
        body_text = text_fetcher(source) or ""
    except Exception as exc:
        return {"verified": False, "reason": "fetch_failed", "error": str(exc), "source": source}
    if not body_text.strip():
        return {"verified": False, "reason": "empty_body_text", "source": source}
    if ticker not in body_text:
        return {"verified": False, "reason": "ticker_not_found_in_body", "ticker": ticker, "source": source}
    return {
        "verified": True,
        "source": {
            **source,
            "body_text": body_text[:MAX_BODY_TEXT_CHARS],
            "verification_status": "ticker_found_in_body",
        },
    }


def _write_json(path: Path | str, payload: Any) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify supplemental research source drafts by checking fetched text for the ticker."
    )
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT_PATH)
    parser.add_argument("--verified-output", type=Path, default=DEFAULT_VERIFIED_OUTPUT_PATH)
    parser.add_argument("--rejected-output", type=Path, default=DEFAULT_REJECTED_OUTPUT_PATH)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    result = verify_supplemental_research_sources(
        input_path=args.input,
        verified_output_path=args.verified_output,
        rejected_output_path=args.rejected_output,
    )
    print(f"supplemental_source_verify_input_count={result['input_count']}")
    print(f"supplemental_source_verify_verified_count={result['verified_count']}")
    print(f"supplemental_source_verify_rejected_count={result['rejected_count']}")
    print(f"verified_output={result['verified_output']}")
    print(f"rejected_output={result['rejected_output']}")
    print("orders_submitted=0")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
