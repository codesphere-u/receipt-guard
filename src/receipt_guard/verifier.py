"""Deterministic OCR receipt/waybill cross-footing verifier and digit-confusion repair solver."""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

# Common thermal-printer / low-DPI OCR character-to-digit confusions
OCR_ALPHA_TO_DIGIT: dict[str, str] = {
    "O": "0", "o": "0", "Q": "0", "D": "0",
    "I": "1", "l": "1", "|": "1", "!": "1",
    "Z": "2", "z": "2",
    "S": "5", "s": "5",
    "G": "6", "b": "6",
    "T": "7",
    "B": "8",
    "g": "9", "q": "9",
}

# Plausible single-digit visual misreads on faded thermal paper
VISUAL_DIGIT_CONFUSIONS: dict[str, tuple[str, ...]] = {
    "0": ("8", "6", "9"),
    "1": ("7", "4"),
    "2": ("7", "3"),
    "3": ("8", "5", "2"),
    "4": ("1", "9"),
    "5": ("6", "8", "3"),
    "6": ("5", "8", "0"),
    "7": ("1", "2"),
    "8": ("0", "3", "6", "9", "5"),
    "9": ("8", "4", "0"),
}


@dataclass(frozen=True)
class OcrLineItem:
    description: str
    raw_qty: str
    raw_unit_price: str
    raw_line_total: str
    ocr_confidence: float = 0.95


@dataclass(frozen=True)
class OcrReceiptInput:
    receipt_id: str
    currency: str
    items: tuple[OcrLineItem, ...]
    raw_subtotal: str | None
    raw_tax: str = "0"
    raw_discount: str = "0"
    raw_grand_total: str = "0"


@dataclass(frozen=True)
class RepairSuggestion:
    field: str
    original_raw: str
    repaired_value: str
    reason: str


@dataclass(frozen=True)
class VerificationVerdict:
    receipt_id: str
    currency: str
    passed: bool
    needs_human_review: bool
    computed_subtotal: Decimal
    parsed_subtotal: Decimal | None
    parsed_tax: Decimal
    parsed_discount: Decimal
    computed_grand_total: Decimal
    parsed_grand_total: Decimal
    discrepancy: Decimal
    errors: tuple[str, ...]
    repairs: tuple[RepairSuggestion, ...]


def clean_ocr_number(raw: str) -> tuple[Decimal, bool]:
    """Normalize an OCR numeric token (fixing O->0, l->1, B->8, S->5 & commas) into exact Decimal."""
    stripped = re.sub(r"^(?:UGX|KES|TZS|NGN|GHS|USD|EUR|Shs\.?|\$)\s*", "", raw.strip(), flags=re.IGNORECASE)
    repaired_chars: list[str] = []
    was_cleaned = False
    for ch in stripped:
        if ch in "0123456789.-":
            repaired_chars.append(ch)
        elif ch in ", ":
            continue
        elif ch in OCR_ALPHA_TO_DIGIT:
            repaired_chars.append(OCR_ALPHA_TO_DIGIT[ch])
            was_cleaned = True
        else:
            was_cleaned = True
    token = "".join(repaired_chars)
    if not token or token in ("-", "."):
        raise ValueError(f"Unparseable OCR numeric token: {raw!r}")
    try:
        return Decimal(token), was_cleaned
    except InvalidOperation as exc:
        raise ValueError(f"Invalid decimal after OCR cleanup: {raw!r} -> {token!r}") from exc


def _find_single_digit_repair(raw_str: str, target_val: Decimal) -> str | None:
    """Check whether flipping one visually confused digit (e.g. 8<->0, 5<->6) yields `target_val`."""
    cleaned_dec, _ = clean_ocr_number(raw_str)
    s = str(cleaned_dec)
    for idx, ch in enumerate(s):
        if ch in VISUAL_DIGIT_CONFUSIONS:
            for alt in VISUAL_DIGIT_CONFUSIONS[ch]:
                cand = s[:idx] + alt + s[idx + 1 :]
                try:
                    if Decimal(cand) == target_val:
                        return cand
                except InvalidOperation:
                    continue
    # Also check missing/extra trailing zero (common VLM hallucination: 150,000 -> 1,500,000)
    if cleaned_dec * Decimal("10") == target_val:
        return str(target_val)
    if cleaned_dec == target_val * Decimal("10"):
        return str(target_val)
    return None


def verify_receipt(
    receipt: OcrReceiptInput,
    *,
    tolerance: Decimal = Decimal("0.01"),
    min_auto_accept_confidence: float = 0.85,
) -> VerificationVerdict:
    """Verify line-item multiplication, subtotal, tax/discount, and grand-total cross-footing."""
    errors: list[str] = []
    repairs: list[RepairSuggestion] = []
    computed_subtotal = Decimal("0")
    low_conf = False

    for idx, item in enumerate(receipt.items, start=1):
        if item.ocr_confidence < min_auto_accept_confidence:
            low_conf = True
        qty, q_clean = clean_ocr_number(item.raw_qty)
        unit, u_clean = clean_ocr_number(item.raw_unit_price)
        line_tot, l_clean = clean_ocr_number(item.raw_line_total)
        norm_reason = "OCR alpha-to-digit normalization"
        if q_clean:
            repairs.append(RepairSuggestion(f"item[{idx}].qty", item.raw_qty, str(qty), norm_reason))
        if u_clean:
            repairs.append(RepairSuggestion(f"item[{idx}].unit_price", item.raw_unit_price, str(unit), norm_reason))
        if l_clean:
            repairs.append(
                RepairSuggestion(f"item[{idx}].line_total", item.raw_line_total, str(line_tot), norm_reason)
            )

        expected_line = qty * unit
        if abs(expected_line - line_tot) > tolerance:
            sug = _find_single_digit_repair(item.raw_line_total, expected_line)
            if sug is not None:
                repairs.append(
                    RepairSuggestion(
                        f"item[{idx}].line_total",
                        item.raw_line_total,
                        sug,
                        f"Single-digit/order-of-magnitude OCR repair restores qty*unit={expected_line}",
                    )
                )
            errors.append(
                f"Line {idx} ('{item.description}') mismatch: {qty} * {unit} = {expected_line}, OCR read {line_tot}"
            )
            computed_subtotal += expected_line
        else:
            computed_subtotal += line_tot

    parsed_sub: Decimal | None = None
    if receipt.raw_subtotal is not None:
        parsed_sub, s_clean = clean_ocr_number(receipt.raw_subtotal)
        if s_clean:
            repairs.append(
                RepairSuggestion("subtotal", receipt.raw_subtotal, str(parsed_sub), "OCR alpha-to-digit normalization")
            )
        if abs(parsed_sub - computed_subtotal) > tolerance:
            errors.append(f"Subtotal mismatch: sum(items)={computed_subtotal}, OCR subtotal={parsed_sub}")

    parsed_tax, _ = clean_ocr_number(receipt.raw_tax)
    parsed_disc, _ = clean_ocr_number(receipt.raw_discount)
    parsed_grand, g_clean = clean_ocr_number(receipt.raw_grand_total)
    if g_clean:
        repairs.append(
            RepairSuggestion(
                "grand_total",
                receipt.raw_grand_total,
                str(parsed_grand),
                "OCR alpha-to-digit normalization",
            )
        )

    computed_grand = computed_subtotal + parsed_tax - parsed_disc
    discrepancy = abs(computed_grand - parsed_grand)
    if discrepancy > tolerance:
        sug = _find_single_digit_repair(receipt.raw_grand_total, computed_grand)
        if sug is not None:
            repairs.append(
                RepairSuggestion(
                    "grand_total",
                    receipt.raw_grand_total,
                    sug,
                    f"OCR visual digit/0-shift repair restores grand total {computed_grand}",
                )
            )
        errors.append(
            f"Grand total mismatch: expected {computed_grand} "
            f"(sub={computed_subtotal} + tax={parsed_tax} - disc={parsed_disc}), OCR read {parsed_grand}"
        )

    passed = len(errors) == 0
    needs_review = (not passed) or low_conf or bool(repairs)
    return VerificationVerdict(
        receipt_id=receipt.receipt_id,
        currency=receipt.currency.upper(),
        passed=passed,
        needs_human_review=needs_review,
        computed_subtotal=computed_subtotal,
        parsed_subtotal=parsed_sub,
        parsed_tax=parsed_tax,
        parsed_discount=parsed_disc,
        computed_grand_total=computed_grand,
        parsed_grand_total=parsed_grand,
        discrepancy=discrepancy,
        errors=tuple(errors),
        repairs=tuple(repairs),
    )
