from app.agents.fact_check_rules import check_numbers
from app.agents.prompts import commentator_prompt, evidence_for_prompt, wording_prompt
from tests.agents.test_fact_checker import MOMENT, insight


def test_integral_evidence_renders_as_integers() -> None:
    assert evidence_for_prompt({"passes": 14.0, "pct": 67.6, "zero": 0.0, "neg": -10.5}) == {"passes": 14, "pct": 67.6, "zero": 0, "neg": -10.5}


def test_commentator_prompt_shows_14_not_14_point_0() -> None:
    prompt = commentator_prompt(MOMENT, {"team": "Kestrel Bay", "opponent": "Ironvale"}, [])
    assert '"pass_streak_passes": 14,' in prompt and "14.0" not in prompt
    assert '"team_possession_pct_window": 67.6' in prompt
    assert "Kestrel Bay" in prompt and "kby" not in prompt.split("moment_id")[0]


def test_wording_prompt_uses_the_same_rendering() -> None:
    prompt = wording_prompt(insight("x"), {"pass_streak_passes": 14.0}, {"team": "Kestrel Bay"})
    assert '"pass_streak_passes": 14}' in prompt


def test_both_renderings_pass_the_number_check() -> None:
    cited = {"pass_streak_passes": 14.0}
    assert check_numbers("14 passes", cited, gate="insight", moment_id="m").ok
    assert check_numbers("14.0 passes", cited, gate="insight", moment_id="m").ok


def test_prompt_mentions_the_most_involved_player_when_known() -> None:
    prompt = commentator_prompt(MOMENT, {"team": "Kestrel Bay", "top_player": "Tomas Vire"}, [])
    assert "Most involved player: Tomas Vire" in prompt
    assert "Most involved player" not in commentator_prompt(MOMENT, {"team": "Kestrel Bay"}, [])
