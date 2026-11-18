import asyncio

import pytest

from missingbe import MissingBe


@pytest.fixture
def sut():
    return MissingBe()


@pytest.fixture
def slept(monkeypatch):
    """Record the delays the request hook waits for, without waiting."""
    delays = []

    async def fake_sleep(seconds):
        delays.append(round(seconds * 1000))

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return delays
