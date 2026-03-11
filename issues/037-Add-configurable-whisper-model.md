# Issue 037: Add Configurable Whisper Model

## Sprint
Sprint 6 — Polish

## Priority
Medium

## References
- docs/15-recommendations.md — #9 (Whisper model selection)

## Description
Make Whisper speech-to-text model selection configurable via `CYRUS_WHISPER_MODEL` env var instead of hardcoded `medium.en`. Support multiple model sizes: `tiny.en`, `base.en`, `small.en`, `medium.en` (default). Allows tuning for hardware constraints and transcription speed vs accuracy tradeoffs.

## Blocked By
- Issue 027 (centralized config)

## Acceptance Criteria
- [ ] `CYRUS_WHISPER_MODEL` env var read in cyrus2/cyrus_config.py
- [ ] Defaults to `medium.en`
- [ ] Valid options: `tiny.en`, `base.en`, `small.en`, `medium.en`
- [ ] Voice module loads specified model on startup
- [ ] Logs model selected at startup
- [ ] Configuration validated (warn on invalid model name)
- [ ] Works on CPU and GPU

## Implementation Steps
1. Add to `cyrus2/cyrus_config.py`:
   ```python
   WHISPER_MODEL = os.environ.get("CYRUS_WHISPER_MODEL", "medium.en")

   VALID_WHISPER_MODELS = ["tiny.en", "base.en", "small.en", "medium.en"]

   if WHISPER_MODEL not in VALID_WHISPER_MODELS:
       print(f"WARN: CYRUS_WHISPER_MODEL={WHISPER_MODEL} not in {VALID_WHISPER_MODELS}")
       print(f"      Using default: medium.en")
       WHISPER_MODEL = "medium.en"
   ```
2. In `cyrus2/cyrus_voice.py` (or brain, wherever Whisper is loaded):
   ```python
   from cyrus_config import WHISPER_MODEL

   def _init_whisper():
       model = WhisperModel(WHISPER_MODEL, device="auto", compute_type="auto")
       print(f"[Voice] Whisper model loaded: {WHISPER_MODEL}")
       return model
   ```
3. Update .env.example:
   ```
   # Whisper speech recognition model
   # Options: tiny.en (fastest, 39M), base.en (244M), small.en (774M), medium.en (1.5GB, default)
   CYRUS_WHISPER_MODEL=medium.en
   ```
4. Add to startup logs:
   ```python
   print(f"[Config] Whisper model: {WHISPER_MODEL}")
   ```

## Files to Create/Modify
- Modify: `cyrus2/cyrus_config.py` (add WHISPER_MODEL, VALID_WHISPER_MODELS)
- Modify: `cyrus2/cyrus_voice.py` (use WHISPER_MODEL when loading model)
- Update: `.env.example` (document CYRUS_WHISPER_MODEL)

## Testing
1. Start voice service with default: `python cyrus2/cyrus_voice.py`
2. Verify logs show "Whisper model loaded: medium.en"
3. Start with `CYRUS_WHISPER_MODEL=tiny.en python cyrus2/cyrus_voice.py`
4. Verify logs show "Whisper model loaded: tiny.en"
5. Verify tiny.en model downloads and loads (much faster than medium)
6. Verify transcription still works correctly
7. Test invalid: `CYRUS_WHISPER_MODEL=invalid python cyrus2/cyrus_voice.py`
8. Verify warning logged and falls back to medium.en
