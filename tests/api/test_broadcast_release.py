"""A subscriber that leaves while the latest moment is still rendering must not leave its queue behind (P4 follow-up)."""

import asyncio

from app.agents.models import FanProfile
from app.api import main as api
from app.api import voice_ws
from app.api.streams import Broadcast


class _SlowRun:
    """Just enough of MatchRun for the fan stream and the voice feed: render_latest never finishes."""

    def __init__(self) -> None:
        self.broadcast = Broadcast()
        self.finished = asyncio.Event()
        self.recaps: dict = {}
        self.metrics: dict = {}
        self.started = asyncio.Event()

    def add_profile(self, fan: FanProfile) -> None:
        pass

    async def render_latest(self, fan: FanProfile):
        self.started.set()
        await asyncio.Event().wait()


async def _cancel_while_rendering(run: _SlowRun, coro) -> None:
    task = asyncio.ensure_future(coro)
    await asyncio.wait_for(run.started.wait(), 2)
    assert run.broadcast.subscriber_count("fan:-|-|casual|en") == 1
    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass


async def test_sse_fan_stream_releases_its_queue_on_early_disconnect(monkeypatch) -> None:
    run = _SlowRun()
    monkeypatch.setattr(api, "get_run", lambda http: run)
    response = await api.stream_fan("-|-|casual|en", http=None)
    await _cancel_while_rendering(run, response.body_iterator.__anext__())
    await response.body_iterator.aclose()
    assert run.broadcast.subscriber_count("fan:-|-|casual|en") == 0


async def test_voice_feed_releases_its_queue_on_early_close() -> None:
    run = _SlowRun()
    await _cancel_while_rendering(run, voice_ws._feed(run, FanProfile(language="en"), asyncio.Queue(), ws=None, state={"busy": False}))
    assert run.broadcast.subscriber_count("fan:-|-|casual|en") == 0


def test_release_is_idempotent() -> None:
    b = Broadcast()
    q = b.open("c")
    b.release("c", q)
    b.release("c", q)
    assert b.subscriber_count("c") == 0
