---
id=016-Fix-file-handle-leak
title=Issue 016: Fix file handle leak
state=GROOMED
parent=
children=
split_count=0
force_split=false
needs_interview=false
verify_count=0
total_input_tokens=38668
total_output_tokens=4
total_duration_seconds=89
total_iterations=1
run_count=1
---

# Issue 016: Fix file handle leak

## Sprint
Sprint 2 — Quality & Safety

## Priority
High

## References
- docs/12-code-audit.md — H4 File Handle Leak

## Description
Fix file handle leak in `cyrus2/cyrus_brain.py:1181` where `open(port_file).read().strip()` is called without a context manager. If `int()` conversion raises an exception, the file handle is never closed. Additionally, add exception handling for missing port file.

## Blocked By
- None

## Acceptance Criteria
- [ ] File handle wrapped in `with` statement
- [ ] Exception handling added for missing/unreadable port file
- [ ] Exception handling added for invalid port number
- [ ] Error messages logged appropriately
- [ ] File handle always closes even on exception
- [ ] Existing port file reading functionality preserved

## Implementation Steps
1. Locate `cyrus_brain.py:1181`:
   ```python
   port = int(open(port_file).read().strip())
   ```
2. Replace with safe version:
   ```python
   try:
       with open(port_file) as f:
           port = int(f.read().strip())
   except FileNotFoundError:
       log.error("Port file not found: %s", port_file)
       raise
   except ValueError:
       log.error("Invalid port number in %s", port_file)
       raise
   except Exception as e:
       log.error("Error reading port file %s: %s", port_file, e)
       raise
   ```
3. Or, if port file absence should fail gracefully:
   ```python
   try:
       with open(port_file) as f:
           port = int(f.read().strip())
   except (FileNotFoundError, ValueError) as e:
       log.warning("Could not read port from %s, using default", port_file)
       port = 8766  # or appropriate default
   ```
4. Verify file handle is closed in all code paths
5. Test with missing file, invalid content, valid content

## Files to Create/Modify
- `cyrus2/cyrus_brain.py` — fix file handle leak at line 1181

## Testing
```bash
# Test with valid port file
echo "8766" > /tmp/test_port.txt
python -c "from cyrus2.cyrus_brain import ...; port = read_port('/tmp/test_port.txt'); print(port)"
# Expected: 8766, no warnings

# Test with missing file (should log error and raise)
python -c "from cyrus2.cyrus_brain import ...; port = read_port('/tmp/nonexistent.txt')" 2>&1 | grep "Port file not found"
# Expected: error logged

# Test with invalid content (should log error and raise)
echo "invalid" > /tmp/test_port.txt
python -c "from cyrus2.cyrus_brain import ...; port = read_port('/tmp/test_port.txt')" 2>&1 | grep "Invalid port"
# Expected: error logged

# Verify file handles closed: run with strace or lsof
lsof -p $(pgrep -f "python cyrus_brain.py") | grep port_file
# Expected: no lingering file descriptors
```

## Stage Log

### GROOMED — 2026-03-11 18:37:46Z

- **From:** NEW
- **Duration in stage:** 89s
- **Input tokens:** 38,668 (final context: 38,668)
- **Output tokens:** 4
- **Iterations:** 1
- **Model:** claude-haiku-4-5-20251001
- **Trigger:** auto/triage
