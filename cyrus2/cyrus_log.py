"""Centralized logging setup for Cyrus.

Call ``setup_logging`` once per entry point, before any other logging calls.
All child loggers (e.g. ``cyrus.brain``, ``cyrus.voice``) inherit from the
configured root logger automatically via Python's logger hierarchy.

Example usage in an entry-point module::

    from cyrus_log import setup_logging
    setup_logging("cyrus")

    import logging
    log = logging.getLogger("cyrus.brain")

Environment variable:
    CYRUS_LOG_LEVEL: ``DEBUG`` | ``INFO`` | ``WARNING`` | ``ERROR``
        Sets the minimum log level.  Defaults to ``INFO``.  Invalid values
        are silently ignored and fall back to ``INFO``.
"""

import logging
import os
import sys


def setup_logging(name: str = "cyrus") -> logging.Logger:
    """Configure and return the named root logger.

    Reads ``CYRUS_LOG_LEVEL`` from the environment (default: ``"INFO"``).
    Invalid values silently fall back to INFO.  At DEBUG level and below,
    a ``HH:MM:SS`` timestamp is prepended to each line; at INFO and above
    the format is compact: ``[name] L message``.

    Args:
        name: Logger name (default ``"cyrus"``).  Pass the same name from
              every entry point so child loggers inherit from it.

    Returns:
        The configured :class:`logging.Logger` instance.
    """
    # Read and validate log level — unknown names fall back to INFO
    level_name = os.environ.get("CYRUS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    # Prepend asctime only at DEBUG and below; keep INFO+ compact
    fmt = "[{name}] {levelname:.1s} {message}"
    if level <= logging.DEBUG:
        fmt = "{asctime} [{name}] {levelname:.1s} {message}"

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(fmt, style="{", datefmt="%H:%M:%S"))

    root = logging.getLogger(name)
    root.setLevel(level)
    root.addHandler(handler)
    root.propagate = False

    return root
