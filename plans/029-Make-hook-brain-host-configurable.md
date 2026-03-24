# Plan 029: Make Hook Brain Host Configurable

## Status: IN PROGRESS

## Gap Analysis

### What Exists
- `cyrus2/cyrus_hook.py` — hook with `BRAIN_HOST = "localhost"` hardcoded (line 32)
- `.env.example` — only contains `ANTHROPIC_API_KEY=`

### What Needs Building
- `BRAIN_HOST` must be read from `CYRUS_BRAIN_HOST` env var (default `"localhost"`)
- `.env.example` must document `CYRUS_BRAIN_HOST`
- Tests must cover: default behaviour, custom host, graceful failure on invalid host

## Prioritized Tasks

- [x] Create plan file
- [x] Write tests for CYRUS_BRAIN_HOST env var support in `cyrus2/tests/test_029_brain_host_configurable.py`
- [x] Modify `cyrus2/cyrus_hook.py` line 32 to read env var
- [x] Update `.env.example` to document `CYRUS_BRAIN_HOST`
- [x] Validate: run lint + tests

## Acceptance-Driven Tests

| Criterion | Test |
|---|---|
| CYRUS_BRAIN_HOST env var read | `test_brain_host_reads_env_var` |
| Defaults to localhost | `test_brain_host_defaults_to_localhost` |
| Hook connects to `{CYRUS_BRAIN_HOST}:8767` | `test_send_uses_brain_host_from_env` |
| Socket timeout respected | `test_send_timeout_still_respected` |
| Documented in .env.example | `test_env_example_documents_cyrus_brain_host` |

## Files to Create/Modify

- **Create**: `cyrus2/tests/test_029_brain_host_configurable.py`
- **Modify**: `cyrus2/cyrus_hook.py` (line 32: read `CYRUS_BRAIN_HOST` env var)
- **Modify**: `.env.example` (add `CYRUS_BRAIN_HOST=localhost` with comment)

## Validation

```bash
cd /home/daniel/Projects/barf/cyrus/cyrus2
uv run ruff check .
uv run ruff format --check .
uv run pytest tests/test_029_brain_host_configurable.py -v
uv run pytest tests/ -v
```

## Open Questions

_None_
