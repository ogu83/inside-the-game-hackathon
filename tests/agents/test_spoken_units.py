"""Spoken text is read verbatim by Voice Live: units must be words, and the number check must accept them."""

from app.agents import prompts
from app.agents.fact_check_rules import extract_numbers


def test_every_spoken_prompt_asks_for_units_as_words() -> None:
    for name in ("COMMENTATOR_INSTRUCTIONS", "PRODUCER_INSTRUCTIONS", "QA_INSTRUCTIONS", "RECAP_INSTRUCTIONS"):
        text = getattr(prompts, name)
        assert prompts.SPOKEN_UNITS in text, name
    assert "metres" in prompts.SPOKEN_UNITS and "metre" in prompts.SPOKEN_UNITS and "never as abbreviations" in prompts.SPOKEN_UNITS


def test_units_as_words_keep_their_unit_family() -> None:
    for text, lang in (("Ironvale moved the ball 76 metres in 85 seconds.", "en"), ("Top 76 metre ilerledi.", "tr")):
        numbers = extract_numbers(text, lang)
        assert any(n.value == 76 for n in numbers), text
