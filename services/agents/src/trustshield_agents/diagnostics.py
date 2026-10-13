"""Count adapter fallbacks (Gemini -> rules/templates) so demos and evals can report them."""

from __future__ import annotations

import logging


class FallbackCounter(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def watch_fallbacks() -> FallbackCounter:
    """Attach a counter to the adapters' loggers (they log a warning/error on every fallback)."""
    counter = FallbackCounter()
    logger = logging.getLogger("trustshield_agents.adapters")
    logger.addHandler(counter)
    logger.propagate = False  # we report a summary instead of a traceback per call
    return counter
