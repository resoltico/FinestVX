---
afad: "3.3"
version: "0.5.0"
domain: SECONDARY
updated: "2026-03-16"
route:
  keywords: [localization boundary, localizationbootconfig, fluentlocalization, parse fluent number, cache stats, cache audit log, message schemas, ftllexengine]
  questions: ["how does finestvx localization work now?", "does finestvx export localization helpers?", "how do i boot a localization runtime?", "where does localized amount parsing live now?", "how do i inspect localization cache audit logs?", "how do legislative packs load FTL resources?"]
---

# FinestVX Localization Boundary

FinestVX does not ship localization constructors, schema validators, or reverse-parsing helpers of
its own. The localization boundary is FTLLexEngine directly.

---

## `FTLLexEngine Localization Boundary`

### Signature
```python
from pathlib import Path

from ftllexengine.localization import FluentLocalization, LocalizationBootConfig
from ftllexengine.parsing import parse_fluent_number

from finestvx.persistence import MANDATED_CACHE_CONFIG
```

### Constraints
- FinestVX exports no localization constructors from `finestvx` or `finestvx.localization`.
- Legislative packs boot localization with `LocalizationBootConfig.from_path(...).boot()`.
- Pack-local boot must apply `MANDATED_CACHE_CONFIG`.
- Reverse parsing comes from `ftllexengine.parsing`, not from FinestVX.
- Cache statistics, cache audit logs, AST access, fallback callbacks, and schema validation are all
  consumed directly from `FluentLocalization`.

### Example
```python
localization = LocalizationBootConfig.from_path(
    locales=("lv_lv", "en_us"),
    resource_ids=("legislation.ftl",),
    base_path=Path("locales/{locale}"),
    cache=MANDATED_CACHE_CONFIG,
).boot()
```
