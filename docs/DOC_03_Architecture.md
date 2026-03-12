---
afad: "3.3"
version: "0.2.0"
domain: PRIMARY
updated: "2026-03-12"
route:
  keywords: [architecture layers, apsw runtime, reader pool, writer thread, lifecycle lock, subinterpreters, python 3.14, observability]
  questions: ["what architecture is implemented today?", "how does concurrency work now?", "where are the python 3.14 features used?", "how do reads and writes interact?", "what observability surfaces exist?"]
---

# FinestVX Architecture Reference

## Implemented Layers

FinestVX implements strictly-isolated layers with a unidirectional dependency graph.

### Core Domain
- immutable accounting objects in `finestvx.core`;
- constructor-driven invariants;
- pure validation helpers and deterministic serialization.

### Persistence
- APSW-backed SQLite WAL store;
- one writer connection plus a read-only reader pool;
- append-only triggers and SQL audit logging;
- reserve-bytes enforcement and WAL-consistent snapshots.

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
- localized decimal, date, currency, and amount parsing.

### Export and Gateway
- deterministic JSON, CSV, XML, and PDF artifacts;
- headless service facade;
- receipt-based storage writes and legislative audit appends.

## Concurrency Model

FinestVX implements single-writer mutation flow with WAL-concurrent reads.

### Writes
- `LedgerRuntime` owns one dedicated writer thread.
- All mutations and snapshots are queued through typed command dataclasses.
- `SqliteLedgerStore` serializes writer-connection access with an internal writer lock.

### Reads
- `SqliteLedgerStore` serves reads from `reader_connection_count` APSW read-only connections.
- Runtime read methods hold only a lifecycle `RWLock.read()` admission lock.
- Reads can proceed while the writer thread is executing queued mutations.

### Shutdown
- `LedgerRuntime.close()` acquires `RWLock.write()` to block new API calls during shutdown.
- Explicit read and write lock timeouts prevent indefinite stalls.

## Python 3.14 Usage

### PEP 750
- `finestvx.persistence.sql` renders validated SQL from template strings.

### PEP 734
- `LegislativeInterpreterRunner` executes pack validation inside fresh subinterpreters.

### PEP 784
- database snapshots use `compression.zstd` for WAL-consistent compressed backups.

## APSW Integration Shape

APSW is used as a first-class architectural boundary, not as a `sqlite3` substitute.

### Connection Topology
- one APSW writer connection for all mutations;
- pooled APSW read-only connections for concurrent snapshots and lookups;
- optional APSW async reader surface via `AsyncLedgerReader`.

### Hardening and Telemetry
- DQS disabled on all connections;
- SQLite log forwarding enabled through APSW library logging;
- `cache_stats()`, `status()`, WAL hook, trace, and profile data surface through `StoreDebugSnapshot`.

### Changesets
- every store mutation returns a `StoreWriteReceipt`;
- receipts include APSW `changeset` and `patchset` bytes plus changed-table metadata.

## Observability Surfaces

- `StoreDebugSnapshot` exposes connection telemetry, counters, reserve bytes, WAL state, and bounded SQL traces.
- `RuntimeDebugSnapshot` exposes queue state and lifecycle-lock telemetry.
- `GatewayDebugSnapshot` exposes runtime state plus registered legislative pack codes.
