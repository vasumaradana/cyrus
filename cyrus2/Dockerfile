FROM python:3.12-slim

# Headless mode — no GUI, audio, or ML hardware required
ENV CYRUS_HEADLESS=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install only the minimal dependencies needed for headless brain operation
COPY requirements-brain-headless.txt .
RUN pip install --no-cache-dir -r requirements-brain-headless.txt

# Copy environment defaults (overridable at runtime via .env volume mount)
COPY .env* ./

# Copy core brain source files
COPY cyrus_brain.py cyrus_hook.py cyrus_config.py cyrus_server.py ./
COPY cyrus_common.py cyrus_log.py ./

# Brain WebSocket server ports:
#   8766 — brain control channel
#   8767 — hook event channel
#   8769 — mobile client channel
#   8770 — extension registration channel
EXPOSE 8766 8767 8769 8770

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8766/health')"

CMD ["python", "cyrus_brain.py"]
