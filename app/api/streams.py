"""One match run: simulate, ingest into the ledger, run the agent pipeline, display behind the delay.

Two modes:
- precompute (default above 1x): every moment is processed before playback starts, so the delayed
  clock only decides when things appear; nothing can be late.
- live (1x, the video): the ingest loop runs `delay_s` ahead of the display loop and each moment is
  processed as it closes. A cue that is not ready when its closing event is displayed is dropped
  and counted; it is never shown late.
"""

import asyncio
import json
import os
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Workflow

from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies, TemplateCommentator, TemplateProducer
from app.agents.models import FanNarrative, FanProfile, MomentResult, OverlayCue
from app.agents.workflow import build_workflow, run_moment
from app.api.clock import BroadcastClock
from app.ledger.labels import moment_labels
from app.ledger.models import CandidateMoment
from app.ledger.state import Ledger
from app.simulator.engine import simulate
from app.simulator.models import MatchEvent
from app.simulator.run import describe

DEFAULT_PROFILES = [FanProfile(language="en"), FanProfile(language="tr")]
END = object()

WorkflowFactory = Callable[[], Workflow]


def template_workflow() -> Workflow:
    return build_workflow(TemplateCommentator(), FactChecker(AlwaysVerifies()))


def workflow_factory_from_env() -> WorkflowFactory:
    if os.environ.get("AGENT_MODE", "template").lower() == "foundry":
        from app.agents.run_match import live_workflow

        return live_workflow
    return template_workflow


class Broadcast:
    """Fan-out of SSE messages per channel. Each subscriber gets its own queue."""

    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self.closed = False

    def publish(self, channel: str, event: str, data: dict[str, Any]) -> None:
        for queue in list(self._queues[channel]):
            queue.put_nowait({"event": event, "data": json.dumps(data, ensure_ascii=False)})

    def close(self) -> None:
        self.closed = True
        for queues in self._queues.values():
            for queue in queues:
                queue.put_nowait(END)

    async def subscribe(self, channel: str) -> AsyncIterator[dict[str, str]]:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[channel].add(queue)
        if self.closed:
            queue.put_nowait(END)
        try:
            while True:
                item = await queue.get()
                if item is END:
                    return
                yield item
        finally:
            self._queues[channel].discard(queue)


@dataclass
class Processed:
    moment: CandidateMoment
    result: MomentResult
    cue: OverlayCue | None
    narratives: list[FanNarrative]
    ready_wall: float


@dataclass
class MatchRun:
    seed: int = 7
    speed: float = 1.0
    delay_s: float = 20.0
    minutes: int = 90
    home: str = "kby"
    away: str = "iva"
    precompute: bool | None = None
    workflow_factory: WorkflowFactory = template_workflow
    profiles: list[FanProfile] = field(default_factory=lambda: list(DEFAULT_PROFILES))

    events: list[MatchEvent] = field(default_factory=list, init=False)
    clock: BroadcastClock | None = field(default=None, init=False)
    broadcast: Broadcast = field(default_factory=Broadcast, init=False)
    processed: dict[str, Processed] = field(default_factory=dict, init=False)
    pending_by_seq: dict[int, list[CandidateMoment]] = field(default_factory=lambda: defaultdict(list), init=False)
    metrics: dict[str, int] = field(default_factory=lambda: defaultdict(int), init=False)
    finished: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _tasks: list[asyncio.Task] = field(default_factory=list, init=False)
    _producer: TemplateProducer = field(default_factory=TemplateProducer, init=False)

    @property
    def match_id(self) -> str:
        return self.events[0].match_id if self.events else f"{self.home}-{self.away}-{self.seed}"

    @property
    def mode(self) -> str:
        return "precompute" if (self.precompute if self.precompute is not None else self.speed > 1) else "live"

    async def start(self) -> None:
        self.events = simulate(self.seed, self.home, self.away, self.minutes)
        loop = asyncio.get_running_loop()
        if self.mode == "precompute":
            ledger = Ledger()
            moments = [m for e in self.events for m in ledger.ingest(e)]
            for moment in moments:
                self.pending_by_seq[moment.window[1]].append(moment)
                await self._process(moment)
            self.clock = BroadcastClock(started_at=loop.time(), speed=self.speed, delay_s=self.delay_s)
        else:
            self.clock = BroadcastClock(started_at=loop.time(), speed=self.speed, delay_s=self.delay_s)
            self._tasks.append(asyncio.create_task(self._ingest_loop()))
        self._tasks.append(asyncio.create_task(self._display_loop()))

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass
        self._finish()

    def _finish(self) -> None:
        if not self.finished.is_set():
            self.finished.set()
            data = {"metrics": self.report()}
            self.broadcast.publish("cues", "match_end", data)
            self.broadcast.publish("events", "match_end", data)
            self.broadcast.close()

    def report(self) -> dict[str, Any]:
        return {**dict(self.metrics), "mode": self.mode, "match_id": self.match_id}

    async def _ingest_loop(self) -> None:
        assert self.clock is not None
        ledger = Ledger()
        loop = asyncio.get_running_loop()
        for event in self.events:
            await asyncio.sleep(max(0.0, self.clock.ingest_wall(event.t) - loop.time()))
            for moment in ledger.ingest(event):
                self.pending_by_seq[moment.window[1]].append(moment)
                self.metrics["moments_detected"] += 1
                self._tasks.append(asyncio.create_task(self._process(moment)))

    async def _process(self, moment: CandidateMoment) -> None:
        labels = moment_labels(moment, (self.home, self.away))
        result = await run_moment(self.workflow_factory(), moment, labels)
        verdict = result.verdict
        self.metrics[f"verdict_{verdict.status}"] += 1
        self.metrics["number_checks"] += len(result.checks)
        self.metrics["number_checks_failed"] += sum(not c.ok for c in result.checks)
        cue, narratives = None, []
        if verdict.status != "rejected" and verdict.insight is not None:
            cue, check = self._producer.cue(verdict.insight, moment, labels)
            self._count(check)
            for profile in self.profiles:
                narrative, check = self._producer.narrative(verdict.insight, moment, labels, profile)
                self._count(check)
                if narrative:
                    narratives.append(narrative)
        self.processed[moment.moment_id] = Processed(moment, result, cue, narratives, asyncio.get_running_loop().time())
        self.broadcast.publish("verdicts", "verdict", {"verdict": verdict.model_dump(), "checks": [c.model_dump() for c in result.checks]})

    def _count(self, check: Any) -> None:
        self.metrics["number_checks"] += 1
        self.metrics["number_checks_failed"] += int(not check.ok)

    async def _display_loop(self) -> None:
        assert self.clock is not None
        loop = asyncio.get_running_loop()
        try:
            for event in self.events:
                await asyncio.sleep(max(0.0, self.clock.display_wall(event.t) - loop.time()))
                self.broadcast.publish("events", "event", self._event_payload(event))
                for moment in self.pending_by_seq.pop(event.seq, []):
                    self._show_or_drop(moment, event)
        finally:
            self._finish()

    def _show_or_drop(self, moment: CandidateMoment, event: MatchEvent) -> None:
        done = self.processed.get(moment.moment_id)
        if done is None:
            self.metrics["cues_dropped_late"] += 1
            self.broadcast.publish("cues", "dropped", {"moment_id": moment.moment_id, "reason": "late", "seq": event.seq})
            return
        if done.cue is None:
            self.metrics["cues_rejected"] += 1
            self.broadcast.publish("cues", "dropped", {"moment_id": moment.moment_id, "reason": done.result.verdict.status, "seq": event.seq, "reasons": done.result.verdict.reasons})
            return
        self.metrics["cues_shown"] += 1
        self.broadcast.publish("cues", "cue", {
            "cue": done.cue.model_dump(), "verdict": done.result.verdict.model_dump(),
            "narratives": [n.model_dump() for n in done.narratives], "minute": event.minute, "second": event.second,
        })

    def _event_payload(self, event: MatchEvent) -> dict[str, Any]:
        return {"seq": event.seq, "minute": event.minute, "second": event.second, "type": event.type, "team_id": event.team_id,
                "player_id": event.player_id, "x": event.x, "y": event.y, "text": describe(event)}
