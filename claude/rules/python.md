---
paths:
  - "**/*.py"
---

# Python style - Leo

Loads only when you touch Python files. Distilled from my actual code in kalshekki
and parlee. Match this; when it conflicts with a specific file, match the file.

## Naming
- `snake_case` for vars/functions - descriptive and explicit over short.
- `PascalCase` for classes/dataclasses. `UPPER_SNAKE_CASE` for constants; `DEFAULT_`
  prefix for calibratable defaults.
- Leading `_` for private helpers/internals. `StrEnum` for string enums.

## Module layout (in order)
1. Rich module docstring - invariants, design rationale, tradeoffs (an essay is fine).
2. `from __future__ import annotations`
3. stdlib → third-party → local imports
4. `__all__ = [...]` - always present and explicit
5. constants / config
6. classes / public functions
7. `_private` helpers last

## Types & data
- Thorough type hints everywhere. mypy strict on core/risk/sensitive modules.
- Frozen, slotted dataclasses for contracts/records:
  `@dataclass(frozen=True, slots=True)`. No post-construction mutation.
- Pydantic for validation/settings with explicit constraints (`Field(ge=0, le=1)`).

## Validation & errors
- Guard clauses first, then logic. Validate at construction/entry.
- Domain-specific exceptions (`ConfigError`, `AdapterError`).
- Error messages always include the bad value and the constraint:
  `raise ValueError(f"sizing_fraction must be in (0, 1], got {sizing_fraction}")`.
- No magic numbers - name every threshold (`ROLLING_CLV_WINDOW = 50`).
- No silent defaults on anything load-bearing; config gets `from_dict` + strict
  `__post_init__` that rejects unknown fields.

## Logging
- `logging.getLogger(__name__)`; structured. No `print()` in library code.

## Tests
- One `test_<module>.py` per source module, mirroring package structure.
- `test_<feature>_<behavior>` names. Boringly explicit: setup → execute → verify.
- Minimal inline factory fixtures (`_pos(...)`, `_intent(...)`). Direct assertions.
- Ships with the code - no module without tests against its acceptance criteria.

## Tooling
- Python 3.12+. `uv` + lockfile. `ruff` (line-length 100, double quotes, select
  E/F/I/UP/B/ASYNC). `pytest` (`-n auto` where it helps).
- Isolate failures: adapters, circuit breakers, error boundaries - no cascades.
