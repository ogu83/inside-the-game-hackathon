from app.agents.fact_check_rules import check_numbers, wording_flags, wording_support
from app.agents.prompts import COMMENTATOR_INSTRUCTIONS, FACT_CHECKER_INSTRUCTIONS, commentator_prompt, evidence_for_prompt, wording_prompt
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


def test_commentator_instructions_are_descriptive_not_evaluative() -> None:
    text = COMMENTATOR_INSTRUCTIONS.casefold()
    for rule in ("descriptive, not evaluative", "dominated", "dictating the tempo", "one-way", "60% or more", "15 passes or more", "copied exactly as digits", "never as words"):
        assert rule in text, rule
    judge = FACT_CHECKER_INSTRUCTIONS.casefold()
    assert "descriptive claim" in judge and "verified" in judge and "do not rewrite for style" in judge and "hints from code" in judge


def test_wording_flags_name_unsupported_evaluative_words() -> None:
    weak = {"pass_streak_passes": 10.0, "pass_streak_duration_s": 40.0}
    assert wording_flags("Kestrel Bay have controlled this spell and are dictating the tempo.", weak) == ["'controlled' (needs possession evidence)", "'dictating' (needs possession evidence)", "'tempo' (needs possession evidence)"]
    assert wording_flags("Kestrel Bay have strung together 10 passes in 40 seconds.", weak) == []
    strong = {"team_possession_pct_window": 68.0, "window_minutes": 5.0}
    assert wording_flags("Kestrel Bay are in control with 68% of the ball.", strong) == []
    assert wording_support({"pass_streak_passes": 15.0}) == {"possession"}
    assert wording_support({"pass_streak_ended_in_shot": 1.0, "pressing_trap_pressures": 3.0}) == {"shot", "pressing"}
    assert wording_flags("Clinical from Ironvale.", {}) == ["'clinical' (needs shot evidence)"]
    assert "'control'" not in str(wording_flags("the controller", {}))


def test_wording_prompt_carries_the_code_hints() -> None:
    prompt = wording_prompt(insight("x"), {"pass_streak_passes": 10.0}, {"team": "Kestrel Bay"}, ["'dominated' (needs possession evidence)"])
    assert "Code flagged unsupported words: 'dominated'" in prompt
    assert "no unsupported evaluative words" in wording_prompt(insight("x"), {}, {})
