---
afad: "3.3"
version: "0.1.0"
domain: PRIMARY
updated: "2026-03-09"
route:
  keywords: [architecture layers, single writer, runtime, subinterpreters, localization, export, debug snapshots, python 3.14]
  questions: ["what architecture is implemented today?", "how does concurrency work?", "where are the python 3.14 features used?", "what layers exist now?", "how is observability exposed?"]
---

# FinestVX Architecture Reference

## Implemented Layers

FinestVX implements six strictly-isolated layers with a unidirectional dependency graph.

### Core Domain
- immutable accounting objects in `finestvx.core`;
- constructor-driven invariants;
- pure validation helpers and deterministic serialization.

### Persistence
- APSW-backed SQLite WAL store;
- STRICT tables;
- append-only protection through SQL triggers;
- SQL audit trail and zstd-backed snapshots.

### Validation
- domain validation reports;
- FTL static validation wrapper over `validate_resource()`;
- legislative result bridging.

### Legislation
- `ILegislativePack` contract;
- default registry bootstrap;
- Latvia `lv.standard.2026` pack;
- subinterpreter-backed isolated validation.

### Presentation and Localization
- strict `FluentLocalization` wrapper;
- pack-local FTL resources;
- fallback observability;
- localized decimal, date, currency, and amount parsing.

### Export and Gateway
- deterministic JSON, CSV, XML, and PDF artifacts;
- headless service facade;
- post-commit legislative audit append;
- runtime and gateway debug snapshots.

## Concurrency Model

FinestVX implements the single-writer, multi-reader concurrency model.

### Writes
- `LedgerRuntime` owns a dedicated write thread.
- All writes are queued through `_WriteCommand` and executed under `RWLock.write()`.
- SQLite write concurrency remains serialized by design.

### Reads
- `LedgerRuntime` serves reads under `RWLock.read()`.
- Book snapshots, audit iteration, and debug snapshots are read-side operations.
- Explicit timeouts are configured for both read and write acquisition paths.

## Python 3.14 Usage

### PEP 750
- `finestvx.persistence.sql` renders validated SQL from template strings.
- Dynamic trigger SQL in the schema layer uses identifier and literal interpolation rules.

### PEP 734
- `LegislativeInterpreterRunner` executes pack validation inside fresh subinterpreters.
- Pack failures do not share interpreter state with the core runtime.

### PEP 784
- database snapshots use `compression.zstd` for WAL-consistent compressed backups.

### Observability
- `StoreDebugSnapshot` captures store counters.
- `RuntimeDebugSnapshot` captures queue and lock state.
- `GatewayDebugSnapshot` exposes runtime state plus registered pack codes.
- These surfaces are non-invasive and safe for production introspection.

## FTLLexEngine Boundaries

FinestVX intentionally delegates security-sensitive and correctness-sensitive work.

### Upstream Responsibilities in Use
- `RWLock` for bounded writer-preference concurrency control;
- `FluentNumber` for float-free value boundaries;
- `FiscalCalendar` and `FiscalPeriod` for fiscal identity;
- ISO validation and locale-aware parsing;
- `FluentLocalization` and `PathResourceLoader` for strict localization;
- graph cycle detection and FTL validation.

### FinestVX Responsibilities
- accounting-domain modeling;
- SQLite schema and persistence policies;
- runtime orchestration;
- legislative-pack bootstrap and audit integration;
- deterministic export and service orchestration.
