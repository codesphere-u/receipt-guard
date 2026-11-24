"""Tests for receipt-guard OCR alpha normalization, cross-footing, 10x/digit repair & CLI."""

from __future__ import annotations

import json
from decimal import Decimal

import pytest

from receipt_guard import OcrLineItem, OcrReceiptInput, clean_ocr_number, verify_receipt
from receipt_guard.cli import main as cli_main


def test_clean_receipt_passes_without_human_review() -> None:
    rec = OcrReceiptInput(
        receipt_id="R-1",
        currency="UGX",
        items=(
            OcrLineItem("Coffee Parchment kg", "10", "8,500", "85,000", 0.99),
            OcrLineItem("Transport Sack", "2", "2,500", "5,000", 0.98),
        ),
        raw_subtotal="90,000",
        raw_tax="0",
        raw_grand_total="90,000",
    )
    v = verify_receipt(rec)
    assert v.passed is True
    assert v.needs_human_review is False
    assert v.computed_grand_total == Decimal("90000")


def test_detects_vlm_10x_hallucination_and_visual_digit_confusion_and_alpha_ocr() -> None:
    val, cleaned = clean_ocr_number("UGX l5,O0O")
    assert val == Decimal("15000") and cleaned is True

    rec = OcrReceiptInput(
        receipt_id="R-BAD",
        currency="UGX",
        items=(OcrLineItem("Item A", "3", "50,000", "150,000"),),
        raw_subtotal="150,000",
        raw_grand_total="180,000",  # 5 misread as 8!
    )
    v = verify_receipt(rec)
    assert v.passed is False
    assert v.needs_human_review is True
    assert any(r.field == "grand_total" and r.repaired_value == "150000" for r in v.repairs)


def test_cli_demo(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["demo"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["passed"] is False
    assert any(r["repaired"] == "150000" for r in out["repairs"])
