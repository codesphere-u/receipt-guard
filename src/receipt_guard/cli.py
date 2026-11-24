"""CLI for receipt-guard."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence

from receipt_guard.verifier import OcrLineItem, OcrReceiptInput, verify_receipt


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="receipt-guard",
        description="Deterministic thermal receipt & invoice OCR cross-footing verifier.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("demo", help="Verify a faded thermal receipt containing OCR O/0 & 10x digit errors")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "demo":
        sample = OcrReceiptInput(
            receipt_id="RCP-KLA-0042",
            currency="UGX",
            items=(
                OcrLineItem("Maize Seed 10kg", "2", "45,OOO", "90,000"),
                OcrLineItem("NPK Fertilizer", "1", "60,000", "60,000"),
            ),
            raw_subtotal="150,000",
            raw_tax="0",
            raw_grand_total="1,500,000",  # Classic VLM 10x zero-hallucination!
        )
        verdict = verify_receipt(sample)
        print(
            json.dumps(
                {
                    "receipt_id": verdict.receipt_id,
                    "passed": verdict.passed,
                    "needs_human_review": verdict.needs_human_review,
                    "computed_grand_total": str(verdict.computed_grand_total),
                    "parsed_grand_total": str(verdict.parsed_grand_total),
                    "errors": list(verdict.errors),
                    "repairs": [
                        {"field": r.field, "original": r.original_raw, "repaired": r.repaired_value, "reason": r.reason}
                        for r in verdict.repairs
                    ],
                },
                indent=2,
            )
        )
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
