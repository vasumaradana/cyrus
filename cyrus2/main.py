"""Cyrus - All-in-one monolith mode (DEPRECATED).

Thin backward-compatibility wrapper. Use split mode instead:
    python cyrus_brain.py &
    python cyrus_voice.py
"""

import asyncio
import sys

from cyrus_brain import main as brain_main


def main() -> None:
    """Warn about deprecation and delegate to cyrus_brain.main."""
    print(
        "\n⚠️  DEPRECATION WARNING: main.py monolith mode is deprecated.\n"
        "Use split mode instead:\n"
        "  python cyrus_brain.py &\n"
        "  python cyrus_voice.py\n"
    )
    asyncio.run(brain_main())


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[Cyrus] Shutting down.")
        sys.exit(0)
