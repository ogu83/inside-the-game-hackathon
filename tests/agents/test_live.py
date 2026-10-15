"""Opt-in tests that call Foundry models: `python -m pytest tests/agents -q -m live`."""

import pytest

from app.agents.run_match import live_workflow, run_moment
from app.ledger.state import detect_all
from app.simulator.engine import simulate

pytestmark = pytest.mark.live


async def test_live_commentator_and_fact_checker_on_three_moments() -> None:
    workflow = live_workflow()
    moments = detect_all(simulate(7))[:3]
    for moment in moments:
        result = await run_moment(workflow, moment)
        assert result.verdict.status in ("verified", "rewritten", "rejected")
        assert result.verdict.attempt in (1, 2)
        assert result.checks and result.checks[0].gate == "insight"
        if result.verdict.status != "rejected":
            assert result.verdict.insight is not None
            assert set(result.verdict.insight.evidence_refs) <= set(moment.evidence)
