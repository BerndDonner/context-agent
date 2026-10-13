"""Human-readable progress on stderr; stdout remains valid JSON."""
from __future__ import annotations

import sys
import time


class Progress:
    def __init__(self) -> None:
        self.started = time.monotonic()

    def __call__(self, message: str) -> None:
        seconds = int(time.monotonic() - self.started)
        print(f'[{seconds // 3600:02d}:{seconds // 60 % 60:02d}:{seconds % 60:02d}] '
              f'{message}', file=sys.stderr, flush=True)
