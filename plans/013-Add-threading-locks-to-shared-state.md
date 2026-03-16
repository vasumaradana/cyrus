# Plan 013: Add threading locks to shared state

## Summary

Add `threading.Lock()` for 5 shared mutable variables and convert `_conversation_active` from `bool` to `threading.Event()` in `cyrus_brain.py`. Wrap all cross-thread reads/writes with `with lock:` blocks. Prevents race conditions between ChatWatcher polling threads, the submit worker thread, the SessionManager scan thread, and the asyncio event loop.

## Dependencies

- None. This issue has no blockers.

## File Path Correction

The issue references `cyrus2/cyrus_brain.py` but the file is at **`cyrus_brain.py`** (project root). The `cyrus2/` directory is empty. All paths in this plan use the correct location.

## Gap Analysis

| Requirement | Current State | Action |
|---|---|---|
| `import threading` | Already present (line 29) | No action needed |
| Lock for `_chat_input_cache` | None | Add `_chat_input_cache_lock = threading.Lock()` |
| Lock for `_vscode_win_cache` | None | Add `_vscode_win_cache_lock = threading.Lock()` |
| Lock for `_chat_input_coords` | None | Add `_chat_input_coords_lock = threading.Lock()` |
| Lock for `_mobile_clients` | None | Add `_mobile_clients_lock = threading.Lock()` |
| Lock for `_whisper_prompt` | None | Add `_whisper_prompt_lock = threading.Lock()` |
| `_conversation_active` as Event | `bool = False` (line 90) | Convert to `threading.Event()` |
| Reads/writes wrapped in locks | Unprotected | Wrap each access site |

## Design Decisions

### D1. Lock granularity — one lock per variable

Each variable gets its own `threading.Lock()`. This matches the existing pattern (`_active_project_lock`, `_project_locked_lock` already exist at lines 82 and 88). Fine-grained locks minimize contention — polling threads don't block the submit thread unnecessarily.

### D2. `threading.Event()` for `_conversation_active`

`threading.Event` is the correct primitive here: it's a boolean flag with atomic `set()`/`clear()`/`is_set()` operations that don't require a `with` block. The variable is only used as a boolean flag — never as a dict or collection — so `Event` is semantically perfect.

Initial state: `threading.Event()` (unset by default) matches the current `bool = False`.

The `global _conversation_active` declarations in `voice_reader` (line 1356) and `routing_loop` (line 1418) become unnecessary for `_conversation_active` because we call methods on the existing object rather than reassigning the name. They will be removed.

### D3. `_conversation_active.wait()` — not applicable

The issue mentions using `.wait()` "where appropriate." After reviewing all access sites, `_conversation_active` is never used in a blocking-wait pattern — it's only checked in `if` conditions within the async routing loop. No `.wait()` calls are warranted; forcing one would change the control flow semantics.

### D4. `_chat_input_coords` polling loop — lock-per-check, not lock-around-loop

At line 1247, `_submit_to_vscode_impl` has `while proj not in _chat_input_coords:` with `time.sleep(0.3)` inside. The lock must protect each individual dict membership check, NOT wrap the entire while loop (which would deadlock by preventing ChatWatcher from writing the coords):

```python
# CORRECT — lock per check:
while True:
    with _chat_input_coords_lock:
        if proj in _chat_input_coords:
            break
    if time.time() >= deadline:
        break
    time.sleep(0.3)
with _chat_input_coords_lock:
    coords = _chat_input_coords.get(proj)
```

### D5. `_mobile_clients` — lock around iteration, not just membership

`_mobile_clients` is a `set()` modified by `add()`, `discard()`, and `difference_update()`. The `_send()` function iterates with `for ws in _mobile_clients.copy()`. The `.copy()` already provides snapshot semantics, but the lock ensures the snapshot is consistent (no add/discard between the truthiness check and the copy). The lock also serializes `add`/`discard`/`difference_update`.

### D6. `_vscode_win_cache` — all accesses on one thread, lock added for safety

All current accesses to `_vscode_win_cache` are in `_submit_to_vscode_impl` which runs on the dedicated submit thread. The lock is still added as defensive hardening — future code changes could introduce cross-thread access.

### D7. `_chat_input_cache` — single write site, lock added for consistency

`_chat_input_cache` is written at line 797 (PermissionWatcher thread) and has no reads in application code. The lock is added for consistency with the other shared variables and to guard against future reads.

## Threading Model — Access Map

### Threads in the system

| Thread | Purpose | Started at |
|---|---|---|
| Main (asyncio event loop) | Runs `voice_reader`, `routing_loop`, `_send`, `handle_mobile_ws` | `asyncio.run(main())` |
| ChatWatcher (N threads, 1 per VS Code window) | Polls UIA tree for chat responses | `ChatWatcher.start()` line 533 |
| PermissionWatcher (N threads, 1 per window) | Polls for permission dialogs | `PermissionWatcher.start()` line 941 |
| SessionManager scan thread | Polls for new VS Code windows | `SessionManager.start()` line 1103 |
| Submit worker thread | Handles VS Code UIA writes | `_submit_worker()` line 1338 |
| Active tracker thread | Tracks focused VS Code window | `_start_active_tracker()` line 1108 |

### Variable access sites

**`_chat_input_cache`** (1 write, 0 reads)

| Line | Access | Thread | Operation |
|---|---|---|---|
| 83 | init | module load | `{}` |
| 797 | write | PermissionWatcher | `_chat_input_cache[self.project_name] = ctrl` |

**`_vscode_win_cache`** (1 read, 2 writes, 1 delete)

| Line | Access | Thread | Operation |
|---|---|---|---|
| 85 | init | module load | `{}` |
| 1271 | read | submit worker | `.get(proj)` |
| 1278 | delete | submit worker | `.pop(proj, None)` |
| 1290 | write | submit worker | `[proj] = win` |

**`_chat_input_coords`** (4 reads, 3 writes) — **genuine cross-thread**

| Line | Access | Thread | Operation |
|---|---|---|---|
| 84 | init | module load | `{}` |
| 547 | read | ChatWatcher | `not in` membership test |
| 556 | write | ChatWatcher | `[self.project_name] = (cx, cy)` |
| 561 | read | ChatWatcher | `.get(self.project_name)` |
| 794 | read | PermissionWatcher | `not in` membership test |
| 801 | write | PermissionWatcher | `[self.project_name] = (cx, cy)` |
| 1247 | read | submit worker | `not in` membership test (in while loop) |
| 1249 | read | submit worker | `.get(proj)` |
| 1263 | write | submit worker | `[proj] = coords` |

**`_mobile_clients`** (2 reads, 3 writes)

| Line | Access | Thread | Operation |
|---|---|---|---|
| 99 | init | module load | `set()` |
| 218 | read | event loop | truthiness + `.copy()` |
| 224 | read | event loop | `for ws in .copy()` |
| 229 | write | event loop | `.difference_update(dead)` |
| 1390 | write | event loop | `.add(ws)` |
| 1409 | write | event loop | `.discard(ws)` |

**`_whisper_prompt`** (2 reads, 1 write) — **genuine cross-thread**

| Line | Access | Thread | Operation |
|---|---|---|---|
| 91 | init | module load | `"Cyrus,"` |
| 1066 | write | scan thread / main | `= f"Cyrus, switch to ..."` |
| 1068 | read | scan thread / main | passed to `_send_threadsafe` |
| 1665 | read | event loop | truthiness check |
| 1666 | read | event loop | value passed to `_send` |

**`_conversation_active`** (1 read, 3 writes)

| Line | Access | Thread | Operation |
|---|---|---|---|
| 90 | init | module load | `False` |
| 1460 | read | event loop | `if _conversation_active:` |
| 1515 | write | event loop | `= False` |
| 1523 | write | event loop | `= spoken.rstrip().endswith("?")` |
| 1545 | write | event loop | `= False` |

## Acceptance Criteria → Test Mapping

| # | Acceptance Criterion | Verification |
|---|---|---|
| AC1 | `import threading` at top | Already present line 29 — `grep "^import threading" cyrus_brain.py` |
| AC2 | Lock for `_chat_input_cache` | `grep "_chat_input_cache_lock" cyrus_brain.py` → definition + 1 usage |
| AC3 | Lock for `_vscode_win_cache` | `grep "_vscode_win_cache_lock" cyrus_brain.py` → definition + 4 usages |
| AC4 | Lock for `_chat_input_coords` | `grep "_chat_input_coords_lock" cyrus_brain.py` → definition + 9 usages |
| AC5 | Lock for `_mobile_clients` | `grep "_mobile_clients_lock" cyrus_brain.py` → definition + 5 usages |
| AC6 | Lock for `_whisper_prompt` | `grep "_whisper_prompt_lock" cyrus_brain.py` → definition + 4 usages |
| AC7 | `_conversation_active` is `threading.Event` | `grep "threading.Event()" cyrus_brain.py` → 1 match |
| AC8 | All reads wrapped in `with lock:` | Grep verification per variable — no bare access outside lock |
| AC9 | All writes wrapped in `with lock:` | Same grep verification |
| AC10 | `.set()` replaces `= True` | `grep "\.set()" cyrus_brain.py` → matches for conditional set |
| AC11 | `.is_set()` replaces `if _conversation_active` | `grep "\.is_set()" cyrus_brain.py` → 1 match at routing check |
| AC12 | `.wait()` used where appropriate | Not applicable (see D3) |
| AC13 | Functionality preserved | Syntax check passes; manual smoke test |
| AC14 | No deadlocks | Lock ordering analysis; no nested locks in any code path |

## Deadlock Risk Analysis

**No risk.** Each lock protects exactly one variable. No code path acquires more than one of the new locks simultaneously. The only pre-existing locks (`_active_project_lock`, `_project_locked_lock`) are never held while acquiring any of the new locks, and vice versa.

The `_chat_input_coords_lock` polling loop (D4) is specifically designed to release the lock between checks to prevent deadlock with ChatWatcher threads.

## Implementation Steps

### Step 1: Add 5 lock definitions

**File**: `cyrus_brain.py`

Add locks immediately after their corresponding variable declarations in the shared state section (lines 79–99):

```python
# ── Shared state ───────────────────────────────────────────────────────────────

_active_project:      str            = ""
_active_project_lock: threading.Lock = threading.Lock()
_chat_input_cache:    dict           = {}   # kept for PermissionWatcher internal use
_chat_input_cache_lock: threading.Lock = threading.Lock()
_chat_input_coords:   dict           = {}   # proj → (cx, cy) pixel coords, cross-thread safe
_chat_input_coords_lock: threading.Lock = threading.Lock()
_vscode_win_cache:    dict           = {}
_vscode_win_cache_lock: threading.Lock = threading.Lock()

_project_locked:      bool           = False
_project_locked_lock: threading.Lock = threading.Lock()

_conversation_active: threading.Event = threading.Event()   # was bool = False
_whisper_prompt:      str  = "Cyrus,"
_whisper_prompt_lock: threading.Lock = threading.Lock()
_tts_active_remote:   bool = False   # True while voice service is playing TTS

# asyncio queues — set in main()
_speak_queue:     asyncio.Queue = None   # (project, text) → sent to voice
_utterance_queue: asyncio.Queue = None   # utterances received from voice

# Mobile WebSocket clients
_mobile_clients: set = set()             # active websocket connections
_mobile_clients_lock: threading.Lock = threading.Lock()
```

**Verify**: `python3 -m py_compile cyrus_brain.py`

### Step 2: Wrap `_chat_input_cache` access (1 site)

**Line 797** — PermissionWatcher `_scan()` method, inside the coord caching block:

```python
# Before:
_chat_input_cache[self.project_name] = ctrl

# After:
with _chat_input_cache_lock:
    _chat_input_cache[self.project_name] = ctrl
```

### Step 3: Wrap `_chat_input_coords` accesses (7 sites)

**Line 547** — ChatWatcher `poll()`, membership test:
```python
# Before:
if self.project_name not in _chat_input_coords:

# After:
with _chat_input_coords_lock:
    _coords_missing = self.project_name not in _chat_input_coords
if _coords_missing:
```

**Line 556** — ChatWatcher `poll()`, coord write:
```python
# Before:
_chat_input_coords[self.project_name] = (
    (r.left + r.right) // 2,
    (r.top + r.bottom) // 2,
)

# After:
with _chat_input_coords_lock:
    _chat_input_coords[self.project_name] = (
        (r.left + r.right) // 2,
        (r.top + r.bottom) // 2,
    )
```

**Line 561** — ChatWatcher `poll()`, coord read for print:
```python
# Before:
print(f"[Brain] {label}Chat input coords cached: "
      f"{_chat_input_coords.get(self.project_name)}")

# After:
with _chat_input_coords_lock:
    _cached = _chat_input_coords.get(self.project_name)
print(f"[Brain] {label}Chat input coords cached: {_cached}")
```

**Line 794** — PermissionWatcher `_scan()`, membership test:
```python
# Before:
if self.project_name not in _chat_input_coords:

# After:
with _chat_input_coords_lock:
    _coords_missing = self.project_name not in _chat_input_coords
if _coords_missing:
```

**Line 801** — PermissionWatcher `_scan()`, coord write:
```python
# Before:
_chat_input_coords[self.project_name] = (
    (r.left + r.right) // 2,
    (r.top + r.bottom) // 2,
)

# After:
with _chat_input_coords_lock:
    _chat_input_coords[self.project_name] = (
        (r.left + r.right) // 2,
        (r.top + r.bottom) // 2,
    )
```

**Lines 1247–1249** — `_submit_to_vscode_impl()`, polling loop + read:
```python
# Before:
deadline = time.time() + 6.0
while proj not in _chat_input_coords and time.time() < deadline:
    time.sleep(0.3)
coords = _chat_input_coords.get(proj)

# After:
deadline = time.time() + 6.0
while time.time() < deadline:
    with _chat_input_coords_lock:
        if proj in _chat_input_coords:
            break
    time.sleep(0.3)
with _chat_input_coords_lock:
    coords = _chat_input_coords.get(proj)
```

**Line 1263** — `_submit_to_vscode_impl()`, fallback coord write:
```python
# Before:
_chat_input_coords[proj] = coords

# After:
with _chat_input_coords_lock:
    _chat_input_coords[proj] = coords
```

### Step 4: Wrap `_vscode_win_cache` accesses (4 sites)

**Line 1234** — Remove `global _vscode_win_cache` declaration (no longer reassigning the dict, only mutating it).

**Line 1271** — read:
```python
# Before:
win = _vscode_win_cache.get(proj)

# After:
with _vscode_win_cache_lock:
    win = _vscode_win_cache.get(proj)
```

**Line 1278** — delete:
```python
# Before:
_vscode_win_cache.pop(proj, None)

# After:
with _vscode_win_cache_lock:
    _vscode_win_cache.pop(proj, None)
```

**Line 1290** — write:
```python
# Before:
_vscode_win_cache[proj] = win

# After:
with _vscode_win_cache_lock:
    _vscode_win_cache[proj] = win
```

### Step 5: Wrap `_mobile_clients` accesses (5 sites)

**Lines 218–229** — `_send()`, broadcast block:
```python
# Before:
if _mobile_clients and msg.get("type") in ("speak", "prompt", "thinking", "tool", "status"):
    mobile_msg = dict(msg)
    if "full_text" in mobile_msg:
        mobile_msg["text"] = mobile_msg.pop("full_text")
    payload = json.dumps(mobile_msg)
    dead = set()
    for ws in _mobile_clients.copy():
        try:
            await ws.send(payload)
        except Exception:
            dead.add(ws)
    _mobile_clients.difference_update(dead)

# After:
with _mobile_clients_lock:
    has_clients = bool(_mobile_clients)
if has_clients and msg.get("type") in ("speak", "prompt", "thinking", "tool", "status"):
    mobile_msg = dict(msg)
    if "full_text" in mobile_msg:
        mobile_msg["text"] = mobile_msg.pop("full_text")
    payload = json.dumps(mobile_msg)
    dead = set()
    with _mobile_clients_lock:
        snapshot = _mobile_clients.copy()
    for ws in snapshot:
        try:
            await ws.send(payload)
        except Exception:
            dead.add(ws)
    if dead:
        with _mobile_clients_lock:
            _mobile_clients.difference_update(dead)
```

**Line 1390** — `handle_mobile_ws()`, add:
```python
# Before:
_mobile_clients.add(ws)

# After:
with _mobile_clients_lock:
    _mobile_clients.add(ws)
```

**Line 1409** — `handle_mobile_ws()`, discard:
```python
# Before:
_mobile_clients.discard(ws)

# After:
with _mobile_clients_lock:
    _mobile_clients.discard(ws)
```

### Step 6: Wrap `_whisper_prompt` accesses (3 sites)

**Lines 1061, 1066–1068** — `SessionManager._add_session()`:
```python
# Before:
global _whisper_prompt
alias = _make_alias(proj)
self._aliases[alias] = proj
print(f"[Brain] Session detected: {proj}  (say \"switch to {alias}\")")
names = " ".join(p for p in self._chat_watchers) + f" {proj}"
_whisper_prompt = f"Cyrus, switch to {names.strip()}."
# Push updated prompt to voice
_send_threadsafe({"type": "whisper_prompt", "text": _whisper_prompt}, loop)

# After (remove global declaration — still needed because of reassignment):
global _whisper_prompt
alias = _make_alias(proj)
self._aliases[alias] = proj
print(f"[Brain] Session detected: {proj}  (say \"switch to {alias}\")")
names = " ".join(p for p in self._chat_watchers) + f" {proj}"
with _whisper_prompt_lock:
    _whisper_prompt = f"Cyrus, switch to {names.strip()}."
    prompt_copy = _whisper_prompt
# Push updated prompt to voice
_send_threadsafe({"type": "whisper_prompt", "text": prompt_copy}, loop)
```

**Lines 1665–1666** — voice connection handler:
```python
# Before:
if _whisper_prompt:
    await _send({"type": "whisper_prompt", "text": _whisper_prompt})

# After:
with _whisper_prompt_lock:
    prompt_copy = _whisper_prompt
if prompt_copy:
    await _send({"type": "whisper_prompt", "text": prompt_copy})
```

### Step 7: Convert `_conversation_active` to `threading.Event` (5 sites)

**Line 90** — declaration (done in Step 1 above):
```python
# Before:
_conversation_active: bool = False

# After:
_conversation_active: threading.Event = threading.Event()   # was bool = False
```

**Line 1356** — `voice_reader()`, remove from global declaration:
```python
# Before:
global _conversation_active, _tts_active_remote

# After:
global _tts_active_remote
```

**Line 1418** — `routing_loop()`, remove from global declaration:
```python
# Before:
global _conversation_active, _active_project

# After:
global _active_project
```

**Line 1460** — `routing_loop()`, read:
```python
# Before:
if _conversation_active:

# After:
if _conversation_active.is_set():
```

**Line 1515** — `routing_loop()`, clear:
```python
# Before:
_conversation_active = False

# After:
_conversation_active.clear()
```

**Line 1523** — `routing_loop()`, conditional set/clear:
```python
# Before:
_conversation_active = spoken.rstrip().endswith("?")

# After:
if spoken.rstrip().endswith("?"):
    _conversation_active.set()
else:
    _conversation_active.clear()
```

**Line 1545** — `routing_loop()`, clear:
```python
# Before:
_conversation_active = False

# After:
_conversation_active.clear()
```

### Step 8: Final verification

```bash
cd /home/daniel/Projects/barf/cyrus

# Syntax check
python3 -m py_compile cyrus_brain.py

# Verify all locks exist
grep -n "_chat_input_cache_lock" cyrus_brain.py
grep -n "_vscode_win_cache_lock" cyrus_brain.py
grep -n "_chat_input_coords_lock" cyrus_brain.py
grep -n "_mobile_clients_lock" cyrus_brain.py
grep -n "_whisper_prompt_lock" cyrus_brain.py

# Verify Event conversion
grep -n "threading.Event()" cyrus_brain.py
grep -n "\.is_set()" cyrus_brain.py
grep -n "\.set()\|\.clear()" cyrus_brain.py

# Verify no bare global reassignment of _conversation_active
grep -n "global _conversation_active" cyrus_brain.py
# Expected: 0 matches (removed from both voice_reader and routing_loop)

# Verify no bare access to locked variables outside of 'with' blocks
# (manual review — grep alone cannot detect this reliably)
```

## Risk Assessment

**Low risk.** All changes are mechanical wrapping of existing reads/writes. No logic changes, no new features, no API changes.

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| Lock held during `await` | Deadlock | None | `_mobile_clients_lock` is a `threading.Lock` used in async code, but we only hold it for instant dict/set operations, never across an `await` |
| `_chat_input_coords` polling deadlock | Thread blocked forever | None | Design D4 — lock released between each check; sleep outside lock |
| Nested lock acquisition | Deadlock | None | No code path acquires more than one new lock; pre-existing locks (`_active_project_lock`, `_project_locked_lock`) are never mixed with new locks |
| `threading.Event` semantic change | Behavior change | Very low | `Event()` starts unset (same as `False`); `.is_set()` returns `bool`; `.set()`/`.clear()` are atomic — semantics match exactly |
| Performance overhead of lock acquisition | Measurable latency | Very low | All locks protect microsecond-scale dict/set operations; polling intervals (0.3–0.5s) dwarf lock overhead |
