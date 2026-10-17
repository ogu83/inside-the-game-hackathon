import json
import pytest

from app.agents.models import MomentResult
from app.agents.workflow import run_moment
from app.ledger.state import detect_all
from app.simulator.engine import simulate
from hosted.src.commentary.main import build_hosted_workflow, create_server, request_json


@pytest.fixture(scope="module")
def sample_moment():
    moments = detect_all(simulate(7))
    return moments[0]


async def test_hosted_workflow_template_mode(sample_moment) -> None:
    workflow = build_hosted_workflow("template")
    assert workflow.name == "commentary"
    result = await run_moment(workflow, sample_moment)
    assert isinstance(result, MomentResult)
    assert result.moment_id == sample_moment.moment_id
    assert result.decision.say is True
    assert result.verdict is not None
    assert result.verdict.status == "verified"


def test_request_json_extraction() -> None:
    class FakeReq:
        def __init__(self, data):
            self.request = data

    assert request_json(FakeReq({"input": '{"test": 1}'})) == '{"test": 1}'
    assert request_json(FakeReq({"input": [{"content": "hello"}]})) == "hello"


def test_create_server_initialization() -> None:
    server = create_server()
    assert server is not None
