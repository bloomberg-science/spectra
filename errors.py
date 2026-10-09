# Copyright 2026 Bloomberg Finance L.P.
# Distributed under the terms of the MIT license.

import logging
import os
import sys
import time

LOG_LEVEL = os.environ.get("BA_LOG_LEVEL", "WARNING").upper()

logging.basicConfig(
    format="[%(levelname)s] %(name)s: %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.WARNING),
    stream=sys.stderr,
)

logger = logging.getLogger("binaryanalysis")


def set_verbose(enabled=True):
    """Turn logging on (INFO/DEBUG) or off (WARNING only)."""
    if enabled:
        env_level = getattr(logging, LOG_LEVEL, logging.INFO)
        logger.setLevel(min(env_level, logging.INFO))
    else:
        logger.setLevel(logging.WARNING)


class ProgressBar:
    """Lightweight progress bar (no external dependencies)."""

    def __init__(self, total, desc="Processing", bar_width=30):
        self.total = total
        self.desc = desc
        self.bar_width = bar_width
        self.current = 0
        self.start_time = time.time()

    def update(self, item_name=""):
        self.current += 1
        elapsed = time.time() - self.start_time
        pct = self.current / self.total if self.total > 0 else 1.0
        filled = int(self.bar_width * pct)
        bar = "█" * filled + "░" * (self.bar_width - filled)

        if self.current > 1 and elapsed > 0:
            rate = elapsed / (self.current - 1)
            remaining = rate * (self.total - self.current)
            eta = f"ETA {remaining:.0f}s"
        else:
            eta = "ETA --"

        label = item_name if len(item_name) <= 30 else "..." + item_name[-27:]
        line = f"\r  {self.desc} [{bar}] {self.current}/{self.total} {eta} | {label}"
        sys.stderr.write(line.ljust(100) + "\r")
        sys.stderr.flush()

    def finish(self):
        elapsed = time.time() - self.start_time
        sys.stderr.write(f"\r  {self.desc}: {self.total} items in {elapsed:.1f}s".ljust(100) + "\n")
        sys.stderr.flush()


class BinaryAnalysisError(Exception):
    pass


class ToolExecutionError(BinaryAnalysisError):
    pass


class DependencyNotFoundError(BinaryAnalysisError):
    pass


class ConfigurationError(BinaryAnalysisError):
    pass
