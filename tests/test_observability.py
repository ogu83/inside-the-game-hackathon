import pytest
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from app.agents.analyst import RuleDirector
from app.agents.fact_checker import FactChecker
from app.agents.fakes import AlwaysVerifies, ScriptedJudge, TemplateCommentator, TemplateRenderer
from app.agents.models import FanProfile, WordingVerdict
from app.agents.producer import Producer
from app.agents.workflow import build_workflow
from app.api.clock import BroadcastClock
from app.api.streams import MatchRun
from app.ledger.mcp_server import LedgerTools
from app.ledger.state import detect_all
from app.observability import init_observability, is_observability_configured, reset_observability
from app.simulator.engine import simulate
from app.voice.qa import QaPipeline, RuleQaAgent, new_question


class DummyView:
    def events(self):
        return simulate(seed=7)[:50]

    def shown_moments(self):
        return []


_EXPORTER = InMemorySpanExporter()
_PROVIDER = TracerProvider()
_PROVIDER.add_span_processor(SimpleSpanProcessor(_EXPORTER))
try:
    trace.set_tracer_provider(_PROVIDER)
except Exception:
    pass


@pytest.fixture
def otel_memory():
    _EXPORTER.clear()
    return _EXPORTER


def test_init_observability_no_env(monkeypatch):
    reset_observability()
    monkeypatch.delenv("APPLICATIONINSIGHTS_CONNECTION_STRING", raising=False)
    monkeypatch.delenv("TRACING", raising=False)
    init_observability()
    assert is_observability_configured() is False


@pytest.mark.asyncio
async def test_moment_span_attributes_and_child_spans(otel_memory):
    events = simulate(seed=7)
    moments = detect_all(events)
    moment = moments[0]

    clock = BroadcastClock(started_at=0.0, speed=1000.0, delay_s=2.0)
    wf_factory = lambda: build_workflow(TemplateCommentator(), FactChecker(AlwaysVerifies()), director=RuleDirector())
    run = MatchRun(
        seed=7,
        workflow_factory=wf_factory,
        producer=Producer(TemplateRenderer()),
        profiles=[FanProfile()],
    )
    run.events = events
    run.clock = clock

    await run._process(moment)

    spans = otel_memory.get_finished_spans()
    moment_spans = [s for s in spans if s.name == f"moment {moment.moment_id}"]
    assert len(moment_spans) == 1
    m_span = moment_spans[0]

    assert m_span.attributes["match.id"] == run.match_id
    assert m_span.attributes["moment.id"] == moment.moment_id
    assert m_span.attributes["moment.kind"] == moment.kind
    assert m_span.attributes["moment.minute"] == float(moment.minute)
    assert m_span.attributes["cue.status"] in ("aired", "skipped")
    assert "moment.latency_ms" in m_span.attributes

    render_spans = [s for s in spans if s.name == "producer.render"]
    assert len(render_spans) >= 1
    for r_span in render_spans:
        assert r_span.parent.span_id == m_span.context.span_id
        assert "profile.key" in r_span.attributes


@pytest.mark.asyncio
async def test_rejected_moment_span_cue_status(otel_memory):
    events = simulate(seed=7)
    moments = detect_all(events)
    moment = moments[0]

    clock = BroadcastClock(started_at=0.0, speed=1000.0, delay_s=2.0)
    rejecting_judge = ScriptedJudge([WordingVerdict(status="rejected", reasons=["failed"])])
    wf_factory = lambda: build_workflow(TemplateCommentator(), FactChecker(rejecting_judge), director=RuleDirector())
    run = MatchRun(
        seed=7,
        workflow_factory=wf_factory,
        producer=Producer(TemplateRenderer()),
        profiles=[FanProfile()],
    )
    run.events = events
    run.clock = clock

    await run._process(moment)

    spans = otel_memory.get_finished_spans()
    moment_spans = [s for s in spans if s.name == f"moment {moment.moment_id}"]
    assert len(moment_spans) == 1
    m_span = moment_spans[0]
    assert m_span.attributes["cue.status"] == "rejected"
    assert m_span.attributes["factcheck.attempts"] >= 1


@pytest.mark.asyncio
async def test_qa_answer_span_and_mcp_tool(otel_memory):
    tools = LedgerTools(DummyView())
    qa = QaPipeline(RuleQaAgent(), FactChecker(AlwaysVerifies()), tools)
    profile = FanProfile(language="en")
    question = new_question(profile.key(), "what is the score?")

    answer = await qa.answer(question, profile)
    assert answer.text

    spans = otel_memory.get_finished_spans()
    qa_spans = [s for s in spans if s.name == "qa.answer"]
    assert len(qa_spans) == 1
    qa_span = qa_spans[0]

    assert qa_span.attributes["qa.language"] == "en"
    assert "score" in qa_span.attributes["qa.tools"]
    assert qa_span.attributes["qa.verdict"] in ("verified", "repaired", "passed")
    assert "qa.timing.draft_ms" in qa_span.attributes
    assert "qa.timing.factcheck_ms" in qa_span.attributes
    assert "qa.timing.total_ms" in qa_span.attributes

    mcp_spans = [s for s in spans if s.name == "mcp.tool score"]
    assert len(mcp_spans) >= 1
    for s in mcp_spans:
        assert s.parent.span_id == qa_span.context.span_id
