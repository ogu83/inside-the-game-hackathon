"""Verify non-blocking precomputed match start for live mode."""

import asyncio
import time

from app.agents.fakes import AlwaysVerifies, TemplateCommentator, TemplateRenderer
from app.agents.models import FanProfile
from app.agents.producer import Producer
from app.agents.workflow import build_workflow
from app.api.streams import MatchRun


class SlowMockCommentator(TemplateCommentator):
    def __init__(self, delay_s: float = 0.5) -> None:
        self.delay_s = delay_s

    async def write(self, moment, labels, feedback):
        await asyncio.sleep(self.delay_s)
        return await super().write(moment, labels, feedback)


def slow_mock_workflow(delay_s: float = 0.5):
    return lambda: build_workflow(SlowMockCommentator(delay_s), FactChecker(AlwaysVerifies()))


from app.agents.fact_checker import FactChecker


async def test_live_accelerated_match_start_is_non_blocking() -> None:
    run = MatchRun(
        seed=7,
        speed=4.0,
        delay_s=20.0,
        minutes=10,
        precompute=True,
        workflow_factory=slow_mock_workflow(delay_s=0.2),
        producer=Producer(TemplateRenderer()),
        agent_mode="foundry",
    )
    t0 = time.perf_counter()
    await run.start()
    elapsed = time.perf_counter() - t0

    try:
        assert elapsed < 0.2, f"run.start() should return immediately without blocking, took {elapsed:.3f}s"
        assert run.clock is not None
        assert run.mode == "precompute"
        await asyncio.sleep(0.5)
        assert len(run.processed) >= 1
    finally:
        await run.stop()
