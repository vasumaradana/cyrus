# Plan 012: Replace print() calls in cyrus_server.py

## Summary

Replace all 4 `print()` calls in `cyrus_server.py` with structured `logging` calls. Add `import logging`, `from cyrus2.cyrus_log import setup_logging`, define `log = logging.getLogger("cyrus.server")` after imports, and call `setup_logging("cyrus")` in `main()`. Convert f-strings to `%s`-style logging. Map each print to the correct log level per docs/16-logging-system.md.

## Dependencies

- **Issue 009** — `cyrus2/cyrus_log.py` must exist with `setup_logging()` function. Plan 009 is complete; module may or may not be built yet. If absent, this issue cannot be verified at runtime but can still be built and syntax-checked.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `import logging` | Not present | Add after `import json` in stdlib imports |
| `from cyrus2.cyrus_log import setup_logging` | Not present | Add after the `websockets` try/except block |
| `log = logging.getLogger("cyrus.server")` | Not present | Add after all imports, before `# ── Config ──` |
| `setup_logging("cyrus")` in `main()` | Not present | Add as first line of `main()` body after arg parsing |
| 4 `print()` calls | All use bare `print()` with `[Brain]` prefix | Convert per mapping table below |
| f-string arguments | All use f-strings | Convert to `%s`-style lazy formatting |

## Design Decisions

### D1. Import location

`import logging` goes with stdlib imports (after `import json`, line 33). `from cyrus2.cyrus_log import setup_logging` goes after the `websockets` try/except block (after line 40). The logger definition `log = logging.getLogger("cyrus.server")` goes immediately after imports, before the `# ── Config (mirrors main.py) ──` section.

### D2. `[Brain]` prefix removal

The `[Brain]` prefix was an ad-hoc convention. The logger name `cyrus.server` now provides this context in the structured format `[cyrus.server] I ...`. Strip `[Brain] ` from all message strings.

### D3. `setup_logging()` placement in `main()`

Place after `argparse` completes but before `asyncio.run(_serve(...))`. This ensures the log call inside `_serve()` uses the configured format.

### D4. No exception handlers to annotate

The only exception handler in the file is `except websockets.ConnectionClosed: pass` (line 141). This is a narrow catch for an expected condition (client disconnect) — not a broad `except Exception`. The `finally` block below it already logs the disconnect via `print()` (being converted to `log.info()`). No `exc_info=True` needed anywhere.

### D5. No silent exception handlers

Unlike cyrus_brain.py and cyrus_voice.py, this file has no silent `except Exception: pass` handlers that need debug logging added.

### D6. Routing decision is DEBUG

Line 139 logs per-utterance routing decisions (`'{text[:50]}' → {decision['action']}`). Per docs/16-logging-system.md, "Routing decisions, command dispatch" maps to DEBUG level. This keeps the default INFO output clean — operators see connects/disconnects but not every utterance.

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Verification |
|---|---|---|
| AC1 | All 4 `print()` calls replaced | `grep -c "print(" cyrus_server.py` → 0 |
| AC2 | `from cyrus2.cyrus_log import setup_logging` added | `grep "from cyrus2.cyrus_log" cyrus_server.py` → match |
| AC3 | `import logging` added | `grep "^import logging" cyrus_server.py` → match |
| AC4 | `log = logging.getLogger("cyrus.server")` defined | `grep 'getLogger("cyrus.server")' cyrus_server.py` → match |
| AC5 | `setup_logging("cyrus")` in `main()` | `grep 'setup_logging("cyrus")' cyrus_server.py` → match |
| AC6 | Server lifecycle events → `log.info()` | Lines 104, 144, 150 use `log.info()` |
| AC7 | Routing decisions → `log.debug()` | Line 139 uses `log.debug()` |
| AC8 | f-strings → `%s` style | All log calls use `log.level("msg: %s", var)` |
| AC9 | No new `print()` introduced | Same grep verification as AC1 |
| AC10 | Functionality unchanged | File structure, function signatures, logic flow all preserved |

## Complete Print-to-Log Mapping (all 4 calls)

### `handle_client()` (3 calls)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 104 | `print(f"[Brain] Client connected: {addr}")` | `log.info("Client connected: %s", addr)` | INFO |
| 139 | `print(f"[Brain] [{project or '?'}] '{text[:50]}' → {decision['action']}")` | `log.debug("[%s] '%s' → %s", project or "?", text[:50], decision["action"])` | DEBUG |
| 144 | `print(f"[Brain] Client disconnected: {addr}")` | `log.info("Client disconnected: %s", addr)` | INFO |

### `_serve()` (1 call)

| Line | Current | Replacement | Level |
|---|---|---|---|
| 150 | `print(f"[Brain] Listening on ws://{host}:{port}")` | `log.info("Listening on ws://%s:%s", host, port)` | INFO |

**Total: 4 calls** (3 + 1 = 4 ✓)

## Implementation Steps

### Step 1: Add imports and logger definition

**File**: `cyrus_server.py`

1. Add `import logging` after `import json` (line 33):

```python
import json
import logging
import re
```

2. Add `from cyrus2.cyrus_log import setup_logging` after the `websockets` try/except block (after line 40):

```python
except ImportError:
    raise SystemExit("websockets not installed — run: pip install websockets")

from cyrus2.cyrus_log import setup_logging
```

3. Add logger definition after the import block, before `# ── Config ──` (line 43):

```python
from cyrus2.cyrus_log import setup_logging

log = logging.getLogger("cyrus.server")


# ── Config (mirrors main.py) ───────────────────────────────────────────────────
```

### Step 2: Add `setup_logging()` call in `main()`

In `main()`, add `setup_logging("cyrus")` after argparse completes, before `asyncio.run()`:

```python
    args = parser.parse_args()

    setup_logging("cyrus")

    asyncio.run(_serve(args.host, args.port))
```

### Step 3: Convert `handle_client()` prints (3 calls)

Line 104:
```python
# Before:
print(f"[Brain] Client connected: {addr}")
# After:
log.info("Client connected: %s", addr)
```

Line 139:
```python
# Before:
print(f"[Brain] [{project or '?'}] '{text[:50]}' → {decision['action']}")
# After:
log.debug("[%s] '%s' → %s", project or "?", text[:50], decision["action"])
```

Line 144:
```python
# Before:
print(f"[Brain] Client disconnected: {addr}")
# After:
log.info("Client disconnected: %s", addr)
```

### Step 4: Convert `_serve()` print (1 call)

Line 150:
```python
# Before:
print(f"[Brain] Listening on ws://{host}:{port}")
# After:
log.info("Listening on ws://%s:%s", host, port)
```

### Step 5: Verify — zero print() calls remaining

```bash
cd /home/daniel/Projects/barf/cyrus
grep -cn "print(" cyrus_server.py
```

Expected: `0` matches.

### Step 6: Verify — all required patterns present

```bash
cd /home/daniel/Projects/barf/cyrus
grep -n "from cyrus2.cyrus_log import setup_logging" cyrus_server.py
grep -n "^import logging" cyrus_server.py
grep -n 'getLogger("cyrus.server")' cyrus_server.py
grep -n 'setup_logging("cyrus")' cyrus_server.py
```

All four must match exactly one line each.

### Step 7: Verify — syntax check

```bash
cd /home/daniel/Projects/barf/cyrus
python3 -m py_compile cyrus_server.py 2>&1 || true
```

Expected: no `SyntaxError`. Import errors for `websockets` are expected if not installed locally.

## Risk Assessment

**Low risk.** Mechanical conversion of 4 print→log calls. No logic changes, no new behavior, no API changes. Smallest file in the migration set.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| `cyrus_log.py` not built yet (Issue 009) | `ImportError` at runtime | Medium | Issue is blocked by 009; builder should verify 009 is complete before runtime test |
| Typo in `%s` format string | Runtime `TypeError` on first log call | Very low | Only 4 calls; mapping table above is exhaustive |
| `project or "?"` evaluated before lazy formatting | Minor — always evaluated | None needed | This is a simple `or` expression, not a function call; negligible cost |
