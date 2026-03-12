---
afad: "3.3"
version: "0.2.0"
domain: AUXILIARY
updated: "2026-03-12"
route:
  keywords: [plugin system, legislative pack, registry copy, subinterpreters, localization assets, extension workflow]
  questions: ["how does the finestvx plugin system work today?", "how do i add a jurisdiction pack?", "why does each pack get its own function registry copy?", "how are packs isolated at runtime?", "what does the service do after posting?"]
---

# FinestVX Plugin System Guide

The plugin system is the legislative-pack layer.

## Pack Contract

A pack must satisfy `ILegislativePack`.
That means it must provide:
- immutable metadata;
- a pack-local `FunctionRegistry` copy;
- `validate_transaction()`;
- `create_localization()`.

## Registration Model

`LegislativePackRegistry` stores packs by `LegislativePackCode`.

Current behavior:
- duplicate codes are rejected;
- unknown codes raise `KeyError`;
- the default registry contains only `LatviaStandard2026Pack`.

## Isolation Model

### Registry Isolation
- the shared FTLLexEngine registry stays frozen;
- each pack receives an unfrozen copy;
- pack-local functions cannot leak into the shared namespace.

### Interpreter Isolation
- `LegislativeInterpreterRunner` validates packs in fresh subinterpreters;
- `validate_transaction_isolated()` is the one-shot wrapper;
- service-level post-commit legislative audit uses the isolated path.

## Latvia 2026 Pack

Current rules:
- `tax_rate`, when present, must equal `Decimal("0.21")`;
- the book must declare `legislative_pack == "lv.standard.2026"`.

Current localization assets:
- Latvian `legislation.ftl`
- English fallback `legislation.ftl`

## Extension Workflow

When adding a new jurisdiction:
1. define `LegislativePackMetadata`;
2. copy the shared function registry;
3. implement validation rules;
4. implement strict pack-local localization loading;
5. register the pack in an explicit bootstrap path;
6. add unit, integration, and isolated-validation tests;
7. update the AFAD documentation set.
