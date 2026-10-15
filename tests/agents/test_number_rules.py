import pytest

from app.agents.fact_check_rules import check_numbers, check_speech, extract_numbers, number_words, round_half_up


def values(text: str, lang: str = "en") -> list[float]:
    return [n.value for n in extract_numbers(text, lang)]


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("kept 68% of the ball", "en", [68.0]),
        ("possession of %68", "en", [68.0]),
        ("yüzde 68 topa sahip", "tr", [68.0]),
        ("yuzde 68 topa sahip", "tr", [68.0]),
        ("68.5 metres forward", "en", [68.5]),
        ("68,5 metre ileri", "tr", [68.5]),
        ("68,5 metres", "en", [68.5]),
        ("1,250 passes", "en", [1250.0]),
        ("1.250 pas", "tr", [1250.0]),
        ("in the 23rd minute, the 14th pass", "en", [23.0, 14.0]),
        ("23. dakikada 14 pas", "tr", [23.0, 14.0]),
        ("14'ü tamamlandı, %68'lik", "tr", [14.0, 68.0]),
        ("a 14-pass move, 2-1 up", "en", [14.0, 2.0, 1.0]),
        ("-10.5 m backwards", "en", [-10.5]),
        ("no numbers here", "en", []),
    ],
)
def test_parser_reads_en_and_tr_formats(text: str, lang: str, expected: list[float]) -> None:
    assert values(text, lang) == expected


def test_identifiers_are_not_numbers() -> None:
    assert values("kby-07 passes to x2 after gpt-5") == []


def test_percent_and_time_units_are_detected() -> None:
    [pct, mins, secs] = extract_numbers("68% in 5 minutes and 85 seconds")
    assert (pct.unit, mins.unit, secs.unit) == ("pct", "min", "s")
    assert extract_numbers("son 5 dakikada %62", "tr")[0].unit == "min"


def test_decimals_are_counted() -> None:
    assert [n.decimals for n in extract_numbers("68 and 68.5 and 68.25")] == [0, 1, 2]


@pytest.mark.parametrize(
    ("text", "lang", "expected"),
    [
        ("six shots and twenty two passes", "en", ["six", "twenty two"]),
        ("one goal in the second half", "en", []),
        ("altmış sekiz pas, iki şut", "tr", ["altmış sekiz", "iki"]),
        ("bir pas, ikinci yarı, yüzde 68", "tr", []),
        ("Altı şut", "tr", ["Altı"]),
        ("on dakika", "tr", ["on"]),
        ("the ball is on the ground", "en", []),
    ],
)
def test_digits_only_rule_finds_number_words(text: str, lang: str, expected: list[str]) -> None:
    assert number_words(text, lang) == expected


def test_round_half_up_is_not_bankers() -> None:
    assert round_half_up(52.5, 0) == 53.0
    assert round_half_up(67.45, 1) == 67.5
    assert round_half_up(2.5, 0) == 3.0


def test_numbers_match_cited_values_after_rounding() -> None:
    cited = {"team_possession_pct_window": 67.6, "pass_streak_progress_m": 52.5}
    assert check_numbers("68% and 52.5 metres", cited, gate="insight", moment_id="m").ok
    assert check_numbers("68% and 53 metres", cited, gate="insight", moment_id="m").ok
    assert not check_numbers("67% of the ball", cited, gate="insight", moment_id="m").ok


def test_seconds_match_in_minutes_only_with_a_minute_unit() -> None:
    cited = {"pass_streak_duration_s": 90.0}
    assert check_numbers("1.5 minutes of passing", cited, gate="insight", moment_id="m").ok
    assert check_numbers("90 seconds of passing", cited, gate="insight", moment_id="m").ok
    assert not check_numbers("1.5 passes", cited, gate="insight", moment_id="m").ok


def test_mismatch_names_the_cited_evidence() -> None:
    check = check_numbers("Ironvale have had 6 shots", {"away_shots_last_10min": 0.0}, gate="insight", moment_id="m")
    assert check.mismatches == ["6 shots does not match the cited shots value (away_shots_last_10min = 0)"]
    assert check_numbers("Ironvale have had 6 shots", {"away_passes": 0.0}, gate="insight", moment_id="m").mismatches == ["6 not in cited evidence (away_passes = 0)"]


def test_number_as_word_fails_even_when_the_value_is_right() -> None:
    check = check_numbers("Ironvale have had six shots", {"away_shots": 6.0}, gate="insight", moment_id="m", profile_key="p")
    assert not check.ok
    assert check.mismatches == ["number written as word: six"]
    assert check.profile_key == "p"


def test_uncited_evidence_does_not_count() -> None:
    assert not check_numbers("14 passes", {}, gate="producer", moment_id="m").ok


def test_turkish_rendering_passes_the_producer_gate() -> None:
    cited = {"team_possession_pct_window": 62.0, "window_minutes": 5.0}
    assert check_numbers("Ironvale son 5 dakikada %62 topa sahip", cited, gate="producer", moment_id="m", lang="tr").ok
    assert not check_numbers("Ironvale son beş dakikada %62 topa sahip", cited, gate="producer", moment_id="m", lang="tr").ok


def test_speech_gate_compares_transcript_with_approved_text() -> None:
    cited = {"pass_streak_passes": 14.0}
    ok = check_speech("Kestrel Bay have strung together 14 passes.", "kestrel bay have strung together 14 passes", cited, moment_id="m", profile_key="p", lang="en")
    assert ok.ok and ok.gate == "speech"
    changed = check_speech("Kestrel Bay have strung together 14 passes.", "Kestrel Bay have strung together 15 passes.", cited, moment_id="m", profile_key="p", lang="en")
    assert changed.mismatches == ["15 passes does not match the cited passes value (pass_streak_passes = 14)", "transcript differs from approved text"]


def test_a_number_must_match_a_cited_value_of_its_own_kind() -> None:
    """The live planted case: a tampered 13 pressures passed because the 13-second window had the same value."""
    cited = {"pressing_trap_pressures": 2.0, "pressing_trap_players": 3.0, "pressing_trap_window_s": 13.0}
    tampered = "Kestrel Bay sprung a pressing trap with 13 pressures from 3 players in 13 seconds."
    check = check_numbers(tampered, cited, gate="producer", moment_id="m")
    assert not check.ok
    assert check.mismatches == ["13 pressures does not match the cited pressures value (pressing_trap_pressures = 2)"]
    honest = "Kestrel Bay sprung a pressing trap with 2 pressures from 3 players in 13 seconds."
    assert check_numbers(honest, cited, gate="producer", moment_id="m").ok


def test_families_are_read_from_the_noun_after_the_number() -> None:
    found = {n.value: n.family for n in extract_numbers("14 passes through 8 players in 52 seconds, 3 shots, 2 pressures, 68% and 40.5 metres over 5 minutes")}
    assert found == {14.0: "passes", 8.0: "players", 52.0: "seconds", 3.0: "shots", 2.0: "pressures", 68.0: "pct", 40.5: "metres", 5.0: "minutes"}
    tr = {n.value: n.family for n in extract_numbers("14 pası 52 saniyede, 3 şut, 2 baskı, 8 oyuncu, %62", "tr")}
    assert tr == {14.0: "passes", 52.0: "seconds", 3.0: "shots", 2.0: "pressures", 8.0: "players", 62.0: "pct"}
    assert extract_numbers("a 14-pass move")[0].family == "passes"
    assert extract_numbers("10 of them")[0].family is None, "no noun, no family: any cited value may justify it"


def test_family_matching_rules() -> None:
    cited = {"pass_streak_passes": 14.0, "pass_streak_duration_s": 52.0}
    assert check_numbers("14 passes in 52 seconds", cited, gate="insight", moment_id="m").ok
    assert check_numbers("14 passes, 14 of them, 14!", cited, gate="insight", moment_id="m").ok, "repeating the same fact is fine"
    assert not check_numbers("52 passes in 14 seconds", cited, gate="insight", moment_id="m").ok, "values swapped between facts"
    uncited_family = check_numbers("14 passes and 3 shots", cited, gate="insight", moment_id="m")
    assert uncited_family.mismatches == ["3 not in cited evidence (pass_streak_passes = 14, pass_streak_duration_s = 52)"]
    assert check_numbers("0.9 minutes of passing", cited, gate="insight", moment_id="m").ok, "seconds cited, minutes spoken"
    assert check_numbers("14 touches", {"pass_streak_passes": 14.0}, gate="insight", moment_id="m").mismatches == ["14 not in cited evidence (pass_streak_passes = 14)"]
