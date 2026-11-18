"""Delay values: a fixed number of milliseconds or a random [min, max] range."""

import json
import random
from dataclasses import dataclass
from typing import Any

FORMAT = "expected milliseconds as a non-negative integer or [min, max]"


class SleepError(ValueError):
    """A sleep value that isn't an integer or a [min, max] pair."""


@dataclass(frozen=True)
class Sleep:
    """A delay in milliseconds: fixed when min_ms == max_ms, else random."""

    min_ms: int
    max_ms: int

    def pick(self, rng: random.Random) -> int:
        return rng.randint(self.min_ms, self.max_ms)


NO_SLEEP = Sleep(0, 0)


def _is_ms(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def parse_sleep(raw: Any) -> Sleep:
    """Parse a decoded JSON sleep value: 500 or [200, 800], in milliseconds."""
    if _is_ms(raw):
        return Sleep(raw, raw)
    if isinstance(raw, list) and len(raw) == 2 and all(_is_ms(v) for v in raw):
        if raw[0] > raw[1]:
            raise SleepError(f"{raw}: min is greater than max")
        return Sleep(raw[0], raw[1])
    raise SleepError(f"{json.dumps(raw)}: {FORMAT}")


def parse_sleep_text(text: str) -> Sleep:
    """Parse a sleep value given as text, such as a query parameter or option."""
    try:
        raw = json.loads(text)
    except json.JSONDecodeError:
        raise SleepError(f"{text!r}: {FORMAT}") from None
    return parse_sleep(raw)
