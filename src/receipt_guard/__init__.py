"""receipt-guard — Deterministic OCR receipt/invoice cross-footing verifier & repair solver."""

from receipt_guard.verifier import (
    OcrLineItem,
    OcrReceiptInput,
    RepairSuggestion,
    VerificationVerdict,
    clean_ocr_number,
    verify_receipt,
)

__version__ = "0.1.0"

__all__ = [
    "OcrLineItem",
    "OcrReceiptInput",
    "RepairSuggestion",
    "VerificationVerdict",
    "__version__",
    "clean_ocr_number",
    "verify_receipt",
]
