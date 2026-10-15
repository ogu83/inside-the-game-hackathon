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
import logging
import os
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Workflow

from app.agents.analyst import PacingTracker, RuleDirector
from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies, TemplateCommentator, TemplateRenderer
from app.agents.models import FanNarrative, FanProfile, MomentResult, OverlayCue
from app.agents.producer import Producer
from app.agents.run_match import close_t
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
log = logging.getLogger(__name__)

WorkflowFactory = Callable[[], Workflow]


def template_workflow() -> Workflow:
    return build_workflow(TemplateCommentator(), FactChecker(AlwaysVerifies()), RuleDirector())


def workflow_factory_from_env() -> WorkflowFactory:
    if os.environ.get("AGENT_MODE", "template").lower() == "foundry":
        from app.agents.run_match import live_workflow

        return live_workflow
    return template_workflow


def template_producer() -> Producer:
    return Producer(TemplateRenderer())


def producer_from_env() -> Producer:
    if os.environ.get("AGENT_MODE", "template").lower() == "foundry":
        from app.agents.run_match import live_producer

        return live_producer()
    return Producer(TemplateRenderer())


class Broadcast:
    """Fan-out of SSE messages per channel. Each subscriber gets its own queue."""

    def __init__(self) -> None:
        self._queues: dict[str, set[asyncio.Queue]] = defaultdict(set)
        self.closed = False
        self._final: tuple[str, dict[str, Any] | None] | None = None

    def publish(self, channel: str, event: str, data: dict[str, Any]) -> None:
        for queue in list(self._queues[channel]):
            queue.put_nowait({"event": event, "data": json.dumps(data, ensure_ascii=False)})

    def close(self, final_event: str | None = None, final_data: dict[str, Any] | None = None) -> None:
        """Send an optional final message to every channel, then end every subscription."""
        self.closed = True
        self._final = (final_event, final_data) if final_event else None
        for channel in list(self._queues):
            if final_event:
                self.publish(channel, final_event, final_data or {})
            for queue in self._queues[channel]:
                queue.put_nowait(END)

    def open(self, channel: str) -> asyncio.Queue:
        """Register a subscriber queue now, so nothing published before iteration starts is lost."""
        queue: asyncio.Queue = asyncio.Queue()
        self._queues[channel].add(queue)
        if self.closed:
            if self._final:
                queue.put_nowait({"event": self._final[0], "data": json.dumps(self._final[1] or {}, ensure_ascii=False)})
            queue.put_nowait(END)
        return queue

    async def drain(self, channel: str, queue: asyncio.Queue) -> AsyncIterator[dict[str, str]]:
        try:
            while True:
                item = await queue.get()
                if item is END:
                    return
                yield item
        finally:
            self._queues[channel].discard(queue)

    def subscribe(self, channel: str) -> AsyncIterator[dict[str, str]]:
        return self.drain(channel, self.open(channel))


@dataclass
class Processed:
    moment: CandidateMoment
    result: MomentResult
    cue: OverlayCue | None
    narratives: list[FanNarrative]
    ready_wall: float
    producer_checks: list = field(default_factory=list)
    dropped_profiles: list[str] = field(default_factory=list)
    displayed: str | None = None  # "shown", "skipped", "rejected", "late" once its closing event has played
    fallback: bool = False

    def timeline(self) -> dict[str, Any]:
        """One moment's agent timeline for the verdict drawer."""
        r = self.result
        return {
            "moment_id": self.moment.moment_id, "kind": self.moment.kind, "team_id": self.moment.team_id, "minute": self.moment.minute,
            "evidence": self.moment.evidence, "top_player_id": self.moment.top_player_id,
            "decision": r.decision.model_dump(),
            "attempts": [a.model_dump() for a in r.attempts],
            "verdict": r.verdict.model_dump() if r.verdict else None,
            "checks": [c.model_dump() for c in r.checks] + [c.model_dump() for c in self.producer_checks],
            "cue": self.cue.model_dump() if self.cue else None,
            "narratives": [n.model_dump() for n in self.narratives],
            "dropped_profiles": self.dropped_profiles,
            "displayed": self.displayed, "fallback": self.fallback,
        }


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
    producer: Producer = field(default_factory=lambda: Producer(TemplateRenderer()))
    profiles: list[FanProfile] = field(default_factory=lambda: list(DEFAULT_PROFILES))
    agent_mode: str = "template"
    fallback_reason: str | None = None

    events: list[MatchEvent] = field(default_factory=list, init=False)
    clock: BroadcastClock | None = field(default=None, init=False)
    broadcast: Broadcast = field(default_factory=Broadcast, init=False)
    processed: dict[str, Processed] = field(default_factory=dict, init=False)
    pending_by_seq: dict[int, list[CandidateMoment]] = field(default_factory=lambda: defaultdict(list), init=False)
    metrics: dict[str, int] = field(default_factory=lambda: defaultdict(int), init=False)
    finished: asyncio.Event = field(default_factory=asyncio.Event, init=False)
    _tasks: list[asyncio.Task] = field(default_factory=list, init=False)
    _pacing: PacingTracker = field(default_factory=PacingTracker, init=False)
    _late: set[str] = field(default_factory=set, init=False)

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
            self.broadcast.close("match_end", {"metrics": self.report()})

    def report(self) -> dict[str, Any]:
        return {**dict(self.metrics), "mode": self.mode, "match_id": self.match_id, "agent_mode": self.agent_mode, "fallback_reason": self.fallback_reason}

    def timelines(self) -> list[dict[str, Any]]:
        return [p.timeline() for p in sorted(self.processed.values(), key=lambda p: p.moment.window[1])]

    def _fall_back(self, reason: str) -> None:
        """Switch to offline agents for the rest of the match (design rule 7) and tell every listener once."""
        if self.agent_mode == "template":
            return
        log.warning("falling back to offline agents: %s", reason)
        self.agent_mode, self.fallback_reason = "template", reason
        self.workflow_factory = template_workflow
        self.producer = Producer(TemplateRenderer(), tamper=self.producer.tamper)
        data = {"reason": reason}
        self.broadcast.publish("cues", "fallback", data)
        self.broadcast.publish("verdicts", "fallback", data)

    def add_profile(self, profile: FanProfile) -> None:
        if profile.key() not in {p.key() for p in self.profiles}:
            self.profiles.append(profile)

    async def render_latest(self, profile: FanProfile) -> FanNarrative | None:
        """Re-render the most recently displayed verified moment for a (new) profile, right away."""
        shown = [p for p in self.processed.values() if p.displayed == "shown" and p.result.verdict and p.result.verdict.insight]
        if not shown:
            return None
        latest = max(shown, key=lambda p: p.moment.window[1])
        existing = next((n for n in latest.narratives if n.profile_key == profile.key()), None)
        if existing is None:
            labels = moment_labels(latest.moment, (self.home, self.away))
            output = await self.producer.render(latest.result.verdict.insight, latest.moment, labels, [profile])
            latest.producer_checks += output.checks
            self.metrics["number_checks"] += len(output.checks)
            self.metrics["number_checks_failed"] += sum(not c.ok for c in output.checks)
            if not output.narratives:
                return None
            existing = output.narratives[0]
            latest.narratives.append(existing)
        return existing

    def narrative_payload(self, narrative: FanNarrative, replay: bool) -> dict[str, Any]:
        done = self.processed[narrative.moment_id]
        event = self.events[done.moment.window[1] - 1]
        return {**narrative.model_dump(), "minute": event.minute, "second": event.second, "replay": replay}

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
        t = close_t(moment, self.events)
        pacing = self._pacing.state_for(moment, t)
        fallback = False
        try:
            result = await run_moment(self.workflow_factory(), moment, labels, pacing)
        except Exception as exc:  # a Foundry error must not take the broadcast down
            self._fall_back(f"agent error: {type(exc).__name__}")
            fallback = True
            result = await run_moment(self.workflow_factory(), moment, labels, pacing)
        self._pacing.record(result.decision, t)
        verdict = result.verdict
        self.metrics["number_checks"] += len(result.checks)
        self.metrics["number_checks_failed"] += sum(not c.ok for c in result.checks)
        cue, narratives = None, []
        if verdict is None:
            self.metrics["moments_skipped"] += 1
            done = Processed(moment, result, None, [], asyncio.get_running_loop().time(), fallback=fallback)
            self.processed[moment.moment_id] = done
            self.broadcast.publish("verdicts", "skipped", done.timeline())
            return
        self.metrics[f"verdict_{verdict.status}"] += 1
        producer_checks, dropped = [], []
        if verdict.status != "rejected" and verdict.insight is not None:
            try:
                output = await self.producer.render(verdict.insight, moment, labels, list(self.profiles))
            except Exception as exc:
                self._fall_back(f"producer error: {type(exc).__name__}")
                fallback = True
                output = await self.producer.render(verdict.insight, moment, labels, list(self.profiles))
            cue, narratives, producer_checks, dropped = output.cue, output.narratives, output.checks, output.dropped_profiles
            self.metrics["number_checks"] += len(output.checks)
            self.metrics["number_checks_failed"] += sum(not c.ok for c in output.checks)
            self.metrics["narratives_dropped"] += len(output.dropped_profiles)
            self.metrics["producer_regenerated"] += output.regenerated
        done = Processed(moment, result, cue, narratives, asyncio.get_running_loop().time(), producer_checks, dropped, fallback=fallback)
        if moment.moment_id in self._late:
            done.displayed = "late"
        self.processed[moment.moment_id] = done
        self.broadcast.publish("verdicts", "verdict", done.timeline())

    async def _display_loop(self) -> None:
        assert self.clock is not None
        loop = asyncio.get_running_loop()
        try:
            for event in self.events:
                await asyncio.sleep(max(0.0, self.clock.display_wall(event.t) - loop.time()))
                self.broadcast.publish("events", "event", self._event_payload(event))
                for moment in self.pending_by_seq.pop(event.seq, []):
                    await self._show_or_drop(moment, event)
        finally:
            self._finish()

    async def _ensure_narratives(self, done: Processed) -> None:
        """Profiles registered after a moment was processed (precompute mode) get their rendering at display time."""
        insight = done.result.verdict.insight if done.result.verdict else None
        if insight is None or done.cue is None:
            return
        have = {n.profile_key for n in done.narratives} | set(done.dropped_profiles)
        missing = [p for p in self.profiles if p.key() not in have]
        if not missing:
            return
        output = await self.producer.render(insight, done.moment, moment_labels(done.moment, (self.home, self.away)), missing)
        done.narratives += output.narratives
        done.dropped_profiles += output.dropped_profiles
        done.producer_checks += output.checks
        self.metrics["number_checks"] += len(output.checks)
        self.metrics["number_checks_failed"] += sum(not c.ok for c in output.checks)
        self.metrics["narratives_dropped"] += len(output.dropped_profiles)

    async def _show_or_drop(self, moment: CandidateMoment, event: MatchEvent) -> None:
        done = self.processed.get(moment.moment_id)
        if done is None:
            self.metrics["cues_dropped_late"] += 1
            self._late.add(moment.moment_id)
            self.broadcast.publish("cues", "dropped", {"moment_id": moment.moment_id, "reason": "late", "seq": event.seq})
            return
        if done.result.verdict is None:
            done.displayed = "skipped"
            self.broadcast.publish("cues", "skipped", {"moment_id": moment.moment_id, "reason": done.result.decision.reason, "seq": event.seq})
            return
        if done.cue is None:
            done.displayed = "rejected"
            self.metrics["cues_rejected"] += 1
            self.broadcast.publish("cues", "dropped", {"moment_id": moment.moment_id, "reason": done.result.verdict.status, "seq": event.seq, "reasons": done.result.verdict.reasons})
            return
        await self._ensure_narratives(done)
        done.displayed = "shown"
        self.metrics["cues_shown"] += 1
        self.broadcast.publish("cues", "cue", {
            "cue": done.cue.model_dump(), "verdict": done.result.verdict.model_dump(),
            "narratives": [n.model_dump() for n in done.narratives], "minute": event.minute, "second": event.second,
        })
        for narrative in done.narratives:
            self.broadcast.publish(f"fan:{narrative.profile_key}", "narrative", self.narrative_payload(narrative, replay=False))

    def _event_payload(self, event: MatchEvent) -> dict[str, Any]:
        return {"seq": event.seq, "minute": event.minute, "second": event.second, "type": event.type, "team_id": event.team_id,
                "player_id": event.player_id, "x": event.x, "y": event.y, "text": describe(event)}
