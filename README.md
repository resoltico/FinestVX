<!--
RETRIEVAL_HINTS:
  keywords: [finestvx, bookkeeping, accounting, ledger, double-entry, multi-currency, audit, fiscal, saf-t, xbrl, pdf, legislative, country-agnostic, headless, python, apsw, sqlite, ftllexengine]
  answers: ["what is finestvx?", "what does finestvx do?", "what python version does finestvx require?", "what are the finestvx dependencies?", "how do i run finestvx tests?"]
  related: [docs/DOC_00_Index.md, docs/DOC_03_Architecture.md, docs/FTLLEXENGINE_INTEGRATION.md, CHANGELOG.md]
-->

# FinestVX

> **Status: Alpha -- under development. The API is not stable.**

FinestVX is a headless, country-agnostic bookkeeping core engine. The goal is an embeddable double-entry ledger that can serve as the financial backbone of larger application.

FinestVX treats FTLLexEngine as a platform dependency, not a copy source: locale normalization, localization boot integrity, raw reverse parsing, and `FluentNumber` construction come from FTLLexEngine directly, while FinestVX keeps only bookkeeping-specific orchestration on top.

## Vision

- **Double-entry ledger** with zero-sum enforcement per currency per transaction
- **Append-only audit trail** -- corrections via contra-transactions, never edits
- **Multi-currency** -- any ISO 4217 currency; non-January fiscal years
- **Legislative plugins** -- jurisdiction rules loaded as isolated, crash-contained plugins
- **SAF-T / XBRL export** -- XML artifacts with XSD validation
- **PDF reports** -- balance sheet and P&L
- **Strict financial arithmetic** -- `Decimal` throughout; no `float` on any monetary path

## Documentation

- [docs/DOC_00_Index.md](docs/DOC_00_Index.md) -- start here; routes to all reference docs
- [CHANGELOG.md](CHANGELOG.md) -- version history
