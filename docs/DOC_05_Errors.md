---
afad: "3.3"
version: "0.7.0"
domain: ERRORS
updated: "2026-03-17"
route:
  keywords: [error model, integrity exceptions, validation reports, apsw errors, localization boot failure, audit enforcement]
  questions: ["what errors does finestvx raise now?", "how do validation reports differ from exceptions?", "how do localization failures surface?", "what happens on append-only violations?", "which FTLLexEngine exceptions are active?"]
---

# FinestVX Error Reference

## Error Categories in Use

### Constructor and Helper Errors
- `TypeError` signals wrong runtime shape or wrong enum/type usage.
- `ValueError` signals violated accounting invariants.
- `KeyError` signals unknown registry or persistence identities.

### Integrity Exceptions
FinestVX uses FTLLexEngine integrity exceptions directly at selected boundaries.

Active interactions:
- `ValidationReport.require_valid()` raises `IntegrityCheckFailedError`.
- `ValidationReport.require_valid()` now captures both `timestamp` and `wall_time_unix` in
  `IntegrityContext` for downstream incident correlation.
- `LocalizationBootConfig.boot()` raises `SyntaxIntegrityError` for Junk resources and
  `IntegrityCheckFailedError` when `required_messages` or `message_schemas` contracts are violated.
- `FluentLocalization.require_clean()` and schema-validation helpers raise
  `IntegrityCheckFailedError` for localization load and contract failures.

- `SqliteLedgerStore.load_book()` raises `LedgerInvariantError` (`ftllexengine.integrity`) when a
  loaded book fails an accounting invariant (unbalanced posted transaction, duplicate account code
  in stored chart); indicates storage corruption or a write-path bug, not user input error.
- `SqliteLedgerStore.load_book()` raises `PersistenceIntegrityError` (`ftllexengine.integrity`) when
  deserialization produces a value that cannot satisfy domain model invariants (unknown currency code,
  precision violation); indicates schema migration gap or storage tampering.
- Both `LedgerInvariantError` and `PersistenceIntegrityError` carry `IntegrityContext` for structured
  audit trail correlation.

### SQLite and APSW Errors
- append-only `UPDATE` or `DELETE` attempts raise `apsw.ConstraintError`.
- invalid persistence writes raise `ValueError` before SQL when the runtime can detect them.

### Concurrency Timeout Errors
- `RWLock.read(timeout=...)` and `RWLock.write(timeout=...)` raise `TimeoutError` when lock acquisition exceeds the configured timeout.
- Public `LedgerRuntime` methods acquire `RWLock.read(timeout=read_lock_timeout)` as a lifecycle gate.
- `LedgerRuntime.close()` acquires `RWLock.write(timeout=write_lock_timeout)` for exclusive shutdown.
- Store reader-pool checkout timeouts surface as `TimeoutError` from `SqliteLedgerStore`.

## Validation Result vs Exception

FinestVX uses both report objects and exceptions intentionally.

### Report Objects
- `ValidationReport` carries core and FTL validation findings.
- `LegislativeValidationResult` carries pack findings.
- report objects are the default shape for caller inspection.

### Exceptions
- constructor and persistence boundary failures fail fast;
- `require_valid()` converts invalid reports into integrity exceptions when a hard-fail boundary is needed.

## Audit and Runtime Boundaries

### Persistence Audit Trail
- core ledger inserts are recorded by SQL triggers;
- post-commit legislative validation results are appended as explicit audit rows;
- audit rows surface as `AuditLogRecord` values rather than exceptions.

### Debug Surfaces
- debug snapshots do not mutate state and do not raise on healthy reads;
- failures inside the underlying store or runtime propagate normally.
