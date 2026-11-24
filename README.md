# receipt-guard

**Deterministic OCR post-processor for thermal receipts, invoices & agro-waybills: exact `Decimal` cross-footing arithmetic verification, OCR digit-confusion repair (`O/0`, `l/1`, `S/5`, `B/8`, 10x zero shifts), and calibrated human-review routing.**

Zero runtime dependencies. Pure Python 3.11+. Stops silent VLM/Tesseract numeric hallucinations (`UGX 150,000` -> `UGX 1,500,000`) from entering microfinance, SACCO, and accounting pipelines.

## Quick Start

```bash
uv sync --extra dev
receipt-guard demo
```

## License

MIT License — see [LICENSE](LICENSE).
