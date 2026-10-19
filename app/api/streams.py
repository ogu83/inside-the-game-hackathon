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
import statistics
import time
from collections import defaultdict
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from agent_framework import Workflow
from opentelemetry import trace

from app.agents.analyst import PacingTracker, RuleDirector
from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies, TemplateCommentator, TemplateRenderer
from app.agents.models import FanNarrative, FanProfile, FullTimeRecap, MomentResult, NumberCheck, OverlayCue, QaTiming, SpeechAudit
from app.agents.producer import Producer
from app.agents.recap import (
    RecapWriter,
    TemplateRecapWriter,
    build_recap_evidence,
    generate_recap,
)
from app.agents.run_match import close_t
from app.agents.workflow import build_workflow, run_moment
from app.api.clock import BroadcastClock
from app.ledger.labels import moment_labels
from app.ledger.mcp_server import LedgerTools
from app.ledger.models import CandidateMoment
from app.simulator.league import CLUBS
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

    def release(self, channel: str, queue: asyncio.Queue) -> None:
        """Drop a subscriber queue (idempotent). Callers that await anything between open() and drain() must call
        this in a finally, or a client that disconnects in that gap leaves a queue collecting messages."""
        self._queues[channel].discard(queue)

    async def drain(self, channel: str, queue: asyncio.Queue) -> AsyncIterator[dict[str, str]]:
        try:
            while True:
                item = await queue.get()
                if item is END:
                    return
                yield item
        finally:
            self.release(channel, queue)

    def subscriber_count(self, channel: str) -> int:
        return len(self._queues[channel])

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
            "displayed": self.displayed or ("rejected" if r.verdict and r.verdict.status == "rejected" else None), "fallback": self.fallback,
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
    plant: int = 0
    workflow_factory: WorkflowFactory = template_workflow
    producer: Producer = field(default_factory=lambda: Producer(TemplateRenderer()))
    profiles: list[FanProfile] = field(default_factory=lambda: list(DEFAULT_PROFILES))
    recap_writer: RecapWriter = field(default_factory=TemplateRecapWriter)
    agent_mode: str = "template"
    fallback_reason: str | None = None
    audits: list[SpeechAudit] = field(default_factory=list, init=False)
    timings: list[QaTiming] = field(default_factory=list, init=False)
    recaps: dict[str, FullTimeRecap] = field(default_factory=dict, init=False)
    recap_checks: list[NumberCheck] = field(default_factory=list, init=False)

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
    _displayed_seq: int = field(default=0, init=False)

    @property
    def match_id(self) -> str:
        return self.events[0].match_id if self.events else f"{self.home}-{self.away}-{self.seed}"

    @property
    def mode(self) -> str:
        return "precompute" if (self.precompute if self.precompute is not None else self.speed > 1) else "live"

    def _wrap_planting(self, factory: WorkflowFactory) -> WorkflowFactory:
        if self.plant <= 0:
            return factory
        from app.agents.planted_errors import PlantPlan, PlantingCommentator
        from app.ledger.state import detect_all
        all_moments = detect_all(self.events)
        plan = PlantPlan.build_demo(all_moments, n=self.plant, seed=self.seed)

        def planting_factory() -> Workflow:
            wf = factory()
            if "commentator" in wf.executors:
                wf.executors["commentator"].writer = PlantingCommentator(
                    wf.executors["commentator"].writer, plan, seed=self.seed, recover=False
                )
            return wf

        return planting_factory

    async def start(self) -> None:
        self.events = simulate(self.seed, self.home, self.away, self.minutes)
        if self.plant > 0:
            self.workflow_factory = self._wrap_planting(self.workflow_factory)
        loop = asyncio.get_running_loop()
        if self.mode == "precompute":
            ledger = Ledger()
            moments = [m for e in self.events for m in ledger.ingest(e)]
            for moment in moments:
                self.pending_by_seq[moment.window[1]].append(moment)
            if self.agent_mode == "template":
                for moment in moments:
                    await self._process(moment)
                self.clock = BroadcastClock(started_at=loop.time(), speed=self.speed, delay_s=self.delay_s)
            else:
                self.clock = BroadcastClock(started_at=loop.time(), speed=self.speed, delay_s=self.delay_s)
                self._tasks.append(asyncio.create_task(self._precompute_pipeline(moments)))
        else:
            self.clock = BroadcastClock(started_at=loop.time(), speed=self.speed, delay_s=self.delay_s)
            self._tasks.append(asyncio.create_task(self._ingest_loop()))
        self._tasks.append(asyncio.create_task(self._display_loop()))

    async def _precompute_pipeline(self, moments: list[CandidateMoment]) -> None:
        for moment in moments:
            if self.finished.is_set():
                break
            await self._process(moment)

    async def stop(self) -> None:
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception as exc:
                log.debug("error waiting for task on stop: %s", exc)
        self._finish()

    def _finish(self) -> None:
        if not self.finished.is_set():
            self.finished.set()
            self.broadcast.close("match_end", {"metrics": self.report()})

    def report(self) -> dict[str, Any]:
        total_cues = self.metrics["cues_shown"] + self.metrics.get("cues_dropped_late", 0)
        ready_share = 1.0 if total_cues == 0 else self.metrics["cues_shown"] / total_cues
        return {
            **dict(self.metrics),
            **self.latency_summary(),
            "ready_before_display_share": round(ready_share, 4),
            "mode": self.mode,
            "match_id": self.match_id,
            "agent_mode": self.agent_mode,
            "fallback_reason": self.fallback_reason,
        }

    def record_timing(self, timing: QaTiming) -> None:
        if timing not in self.timings:
            self.timings.append(timing)

    def latency_summary(self) -> dict[str, int]:
        """p50 of pressed-to-answer and pressed-to-speech over this match (criterion 9 asks for about 3 s median)."""
        answers = [t.answer_ms() for t in self.timings if t.answer_ms() is not None]
        speech = [t.speech_ms() for t in self.timings if t.speech_ms() is not None]
        out: dict[str, int] = {}
        if answers:
            out["qa_answer_p50_ms"] = round(statistics.median(answers))
        if speech:
            out["qa_speech_p50_ms"] = round(statistics.median(speech))
        return out

    def timelines(self, playback_t: float | None = None) -> list[dict[str, Any]]:
        if self.finished.is_set():
            return [p.timeline() for p in sorted(self.processed.values(), key=lambda p: p.moment.window[1])]
        if self.clock is None:
            return []
        if playback_t is None:
            playback_t = self.clock.playback_t(time.monotonic())
        shown = []
        for p in self.processed.values():
            if not self.events or p.moment.window[1] > len(self.events):
                continue
            closing_t = self.events[p.moment.window[1] - 1].t
            if closing_t <= playback_t:
                shown.append(p)
        return [p.timeline() for p in sorted(shown, key=lambda p: p.moment.window[1])]

    # LedgerView for the MCP tools and the Q&A agent: only what the broadcast has shown.
    def displayed_events(self) -> list[MatchEvent]:
        if self.clock is None:
            return []
        if self.finished.is_set():
            return list(self.events)
        playback = self.clock.playback_t(time.monotonic())  # the loop clock is time.monotonic(); this also works from sync code
        return [e for e in self.events if e.t <= playback]

    def shown_moments(self) -> list[dict[str, Any]]:
        shown = sorted((p for p in self.processed.values() if p.displayed == "shown" and p.result.verdict and p.result.verdict.insight), key=lambda p: p.moment.window[1])
        rows = []
        for p in shown:
            insight = p.result.verdict.insight
            tr = next((n.text for n in p.narratives if n.profile_key.endswith("|tr")), None)
            rows.append({"moment_id": p.moment.moment_id, "minute": float(p.moment.minute), "kind": p.moment.kind, "team_id": p.moment.team_id,
                         "team": CLUBS[p.moment.team_id].short if p.moment.team_id in CLUBS else p.moment.team_id,
                         "claim": insight.claim, "why_it_matters": insight.why_it_matters, "narrative_tr": tr, "evidence": p.moment.evidence})
        return rows

    def tools(self) -> LedgerTools:
        return LedgerTools(_RunView(self))

    def record_audit(self, audit: SpeechAudit) -> None:
        self.audits.append(audit)
        self.metrics["speech_checks"] += 1
        self.metrics["speech_mismatches"] += int(not audit.ok)
        if audit.question_id and not audit.question_id.startswith("nh-"):
            self.metrics["answers_spoken"] += 1

    def mark_interrupted(self, ref: str) -> SpeechAudit | None:
        """The fan barged in while the line `ref` (a moment id or question id) was still playing in the browser: the
        server had long finished sending it, so only the page knows. Marks the latest audit of that line."""
        for audit in reversed(self.audits):
            if ref in (audit.moment_id, audit.question_id):
                if not audit.interrupted:
                    audit.interrupted = True
                    self.metrics["lines_interrupted"] += 1
                return audit
        return None

    def _fall_back(self, reason: str) -> None:
        """Switch to offline agents for the rest of the match (design rule 7) and tell every listener once."""
        if self.agent_mode == "template":
            return
        log.warning("falling back to offline agents: %s", reason)
        self.agent_mode, self.fallback_reason = "template", reason
        self.workflow_factory = self._wrap_planting(template_workflow) if self.plant > 0 else template_workflow
        self.producer = Producer(TemplateRenderer(), tamper=self.producer.tamper)
        self.recap_writer = TemplateRecapWriter()
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
                if profile.depth == "analyst":
                    casual = next((n for n in latest.narratives if n.profile_key.endswith(f"|casual|{profile.language}") or n.profile_key.endswith(f"|{profile.language}")), None)
                    if casual is not None:
                        existing = FanNarrative(moment_id=latest.moment.moment_id, profile_key=profile.key(), text=casual.text)
                        latest.narratives.append(existing)
                        return existing
                return None
            existing = output.narratives[0]
            latest.narratives.append(existing)
        return existing

    async def render_recap(self, profile: FanProfile, moments: list[CandidateMoment] | None = None) -> FullTimeRecap:
        if profile.key() in self.recaps:
            return self.recaps[profile.key()]
        if moments is None:
            moments = [p.moment for p in self.processed.values() if p.displayed == "shown"]
        evidence, labels = build_recap_evidence(
            self.events,
            moments=moments,
            home=self.home,
            away=self.away,
            profile=profile,
        )
        try:
            recap, checks = await generate_recap(self.recap_writer, evidence, labels, profile)
        except Exception as exc:
            self._fall_back(f"recap error: {type(exc).__name__}")
            recap, checks = await generate_recap(TemplateRecapWriter(), evidence, labels, profile)
        self.recaps[profile.key()] = recap
        self.recap_checks += checks
        self.metrics["number_checks"] += len(checks)
        self.metrics["number_checks_failed"] += sum(not c.ok for c in checks)
        return recap

    async def _deliver_recap(self) -> None:
        moments = [p.moment for p in self.processed.values() if p.displayed == "shown"]
        for profile in list(self.profiles):
            recap = await self.render_recap(profile, moments=moments)
            self.broadcast.publish(f"fan:{profile.key()}", "recap", recap.model_dump())

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
                self._on_moment_detected(moment)

    def _on_moment_detected(self, moment: CandidateMoment) -> None:
        """Queue a detected moment for display, or count it as late at once when its closing event has already aired
        (tiny delays: the display loop can pass the closing seq before the ingest loop sees it)."""
        self.metrics["moments_detected"] += 1
        if moment.window[1] <= self._displayed_seq:
            self.metrics["cues_dropped_late"] += 1
            self._late.add(moment.moment_id)
            self.broadcast.publish("cues", "dropped", {"moment_id": moment.moment_id, "reason": "late", "seq": moment.window[1]})
        else:
            self.pending_by_seq[moment.window[1]].append(moment)
        self._tasks.append(asyncio.create_task(self._process(moment)))

    async def _process(self, moment: CandidateMoment) -> None:
        tracer = trace.get_tracer("app.api.streams")
        with tracer.start_as_current_span(f"moment {moment.moment_id}") as span:
            span.set_attribute("match.id", self.match_id)
            span.set_attribute("moment.id", moment.moment_id)
            span.set_attribute("moment.kind", moment.kind)
            span.set_attribute("moment.minute", float(moment.minute))
            t_start = asyncio.get_running_loop().time()
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
            latency_ms = round((asyncio.get_running_loop().time() - t_start) * 1000, 2)
            span.set_attribute("moment.latency_ms", latency_ms)
            if verdict is None:
                span.set_attribute("cue.status", "skipped")
                self.metrics["moments_skipped"] += 1
                done = Processed(moment, result, None, [], asyncio.get_running_loop().time(), fallback=fallback)
                self.processed[moment.moment_id] = done
                if self.mode != "precompute":
                    self.broadcast.publish("verdicts", "skipped", done.timeline())
                return
            span.set_attribute("factcheck.layer", verdict.layer)
            span.set_attribute("factcheck.attempts", verdict.attempt)
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
            cue_status = "aired" if cue is not None else ("rejected" if verdict.status == "rejected" else "rejected")
            span.set_attribute("cue.status", cue_status)
            done = Processed(moment, result, cue, narratives, asyncio.get_running_loop().time(), producer_checks, dropped, fallback=fallback)
            if moment.moment_id in self._late:
                done.displayed = "late"
            self.processed[moment.moment_id] = done
            if self.mode != "precompute":
                self.broadcast.publish("verdicts", "verdict", done.timeline())

    async def _display_loop(self) -> None:
        assert self.clock is not None
        loop = asyncio.get_running_loop()
        try:
            for event in self.events:
                await asyncio.sleep(max(0.0, self.clock.display_wall(event.t) - loop.time()))
                self._displayed_seq = event.seq
                self.broadcast.publish("events", "event", self._event_payload(event))
                for moment in self.pending_by_seq.pop(event.seq, []):
                    await self._show_or_drop(moment, event)
            await self._deliver_recap()
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
            self.broadcast.publish("verdicts", "skipped", done.timeline())
            return
        if done.cue is None:
            done.displayed = "rejected"
            self.metrics["cues_rejected"] += 1
            self.broadcast.publish("cues", "dropped", {"moment_id": moment.moment_id, "reason": done.result.verdict.status, "seq": event.seq, "reasons": done.result.verdict.reasons})
            self.broadcast.publish("verdicts", "verdict", done.timeline())
            return
        await self._ensure_narratives(done)
        for profile in self.profiles:
            if profile.depth == "analyst":
                has_narrative = any(n.profile_key == profile.key() for n in done.narratives)
                if not has_narrative:
                    casual = next((n for n in done.narratives if n.profile_key.endswith(f"|casual|{profile.language}") or n.profile_key.endswith(f"|{profile.language}")), None)
                    if casual is not None:
                        done.narratives.append(FanNarrative(moment_id=done.moment.moment_id, profile_key=profile.key(), text=casual.text))
        done.displayed = "shown"
        self.metrics["cues_shown"] += 1
        self.broadcast.publish("cues", "cue", {
            "cue": done.cue.model_dump(), "verdict": done.result.verdict.model_dump(),
            "narratives": [n.model_dump() for n in done.narratives], "minute": event.minute, "second": event.second,
        })
        for narrative in done.narratives:
            self.broadcast.publish(f"fan:{narrative.profile_key}", "narrative", self.narrative_payload(narrative, replay=False))
        self.broadcast.publish("verdicts", "verdict", done.timeline())

    def _event_payload(self, event: MatchEvent) -> dict[str, Any]:
        return {"seq": event.seq, "minute": event.minute, "second": event.second, "type": event.type, "team_id": event.team_id,
                "player_id": event.player_id, "x": event.x, "y": event.y, "text": describe(event)}


class _RunView:
    """LedgerView adapter: `events` is the dataclass field on MatchRun, so the view maps the protocol names."""

    def __init__(self, run: MatchRun) -> None:
        self.run = run

    def events(self) -> list[MatchEvent]:
        return self.run.displayed_events()

    def shown_moments(self) -> list[dict[str, Any]]:
        return self.run.shown_moments()
