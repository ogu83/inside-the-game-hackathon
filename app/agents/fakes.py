"""Model-free agents: deterministic templates for offline mode, and scripted doubles for tests.

Offline mode is what `docker compose` runs without Azure and what the API falls back to when no
model is configured. Every template still passes through the same Fact-Checker gates.
"""

from collections.abc import Callable

from app.agents.fact_check_rules import check_rendering
from app.agents.models import FanNarrative, FanProfile, Insight, NumberCheck, OverlayCue, WordingVerdict
from app.ledger.models import CandidateMoment

Tamper = Callable[[str, str, str, str], str]  # (text, moment_id, profile_key, lang) -> text; test hook for planted errors


def _n(value: float) -> str:
    return f"{value:g}"


def _shorten(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[: limit - 1].rsplit(" ", 1)[0]
    return cut.rstrip(",.;:") + "..."


class TemplateCommentator:
    """Fills a fixed sentence from the evidence. Numbers are copied, never computed."""

    async def write(self, moment: CandidateMoment, labels: dict[str, str], feedback: list[str]) -> Insight:
        e = moment.evidence
        team = labels.get("team", moment.team_id)
        streak_keys = ("pass_streak_passes", "pass_streak_players", "pass_streak_duration_s")
        if moment.kind == "pass_streak" and all(k in e for k in streak_keys):
            passes, players, duration = (_n(e[k]) for k in streak_keys)
            claim = f"{team} have strung together {passes} passes through {players} players in {duration} seconds."
            refs = ["pass_streak_passes", "pass_streak_players", "pass_streak_duration_s"]
            if labels.get("angle") == "player" and labels.get("top_player") and "top_player_passes" in e:
                claim = f"{team} have strung together {passes} passes in {duration} seconds, {_n(e['top_player_passes'])} of them from {labels['top_player']}."
                refs = ["pass_streak_passes", "pass_streak_duration_s", "top_player_passes"]
            if e.get("pass_streak_ended_in_shot"):
                why = "Patient possession turned into a shot, which is exactly what this build-up is for."
            elif e.get("window_minutes", 0) >= 3 and "team_possession_pct_window" in e:
                why = f"It comes with {_n(e['team_possession_pct_window'])}% of the ball over the last {_n(e['window_minutes'])} minutes, so {labels.get('opponent', 'the opposition')} are chasing."
                refs += ["team_possession_pct_window", "window_minutes"]
            else:
                why = "An early statement of intent: they want the ball and are keeping it."
            return Insight(moment_id=moment.moment_id, claim=claim, why_it_matters=why, evidence_refs=refs, confidence=0.9)
        trap_keys = ("pressing_trap_pressures", "pressing_trap_window_s", "pressing_trap_regain_distance_to_goal_m")
        if moment.kind == "pressing_trap" and all(k in e for k in trap_keys):
            presses, window, dist = (_n(e[k]) for k in trap_keys)
            who = labels.get("top_player", team)
            claim = f"{team} pressed {presses} times in {window} seconds and {who} won the ball {dist} metres from goal."
            why = f"That is the pressing trap closing on {labels.get('opponent', 'the opposition')} in their own build-up: win it high, attack a disorganised defence."
            return Insight(moment_id=moment.moment_id, claim=claim, why_it_matters=why, evidence_refs=list(trap_keys), confidence=0.85)
        key, value = next(iter(e.items()))
        return Insight(moment_id=moment.moment_id, claim=f"{team}: {key.replace('_', ' ')} at {_n(value)}.", why_it_matters="A notable moment.", evidence_refs=[key], confidence=0.5)


class ScriptedCommentator:
    """Returns prepared insights in order; the last one repeats. For tests of the retry edge."""

    def __init__(self, insights: list[Insight]) -> None:
        self.insights = list(insights)
        self.calls: list[list[str]] = []

    async def write(self, moment: CandidateMoment, labels: dict[str, str], feedback: list[str]) -> Insight:
        self.calls.append(list(feedback))
        index = min(len(self.calls) - 1, len(self.insights) - 1)
        return self.insights[index].model_copy(update={"moment_id": moment.moment_id})


class AlwaysVerifies:
    async def judge(self, insight: Insight, cited: dict[str, float], labels: dict[str, str]) -> WordingVerdict:
        return WordingVerdict(status="verified")


class ScriptedJudge:
    def __init__(self, verdicts: list[WordingVerdict]) -> None:
        self.verdicts = list(verdicts)
        self.calls = 0

    async def judge(self, insight: Insight, cited: dict[str, float], labels: dict[str, str]) -> WordingVerdict:
        verdict = self.verdicts[min(self.calls, len(self.verdicts) - 1)]
        self.calls += 1
        return verdict


class TemplateProducer:
    """Renders a verified insight as an OverlayCue and a FanNarrative per profile, each number-checked.

    `tamper` is applied to every rendering before its gate; the planted-error harness uses it to
    corrupt renderings (changed number, dropped number, number as a word) and count what the gate catches.
    """

    def __init__(self, tamper: Tamper | None = None) -> None:
        self.tamper = tamper

    def _text(self, text: str, moment_id: str, profile_key: str, lang: str) -> str:
        return self.tamper(text, moment_id, profile_key, lang) if self.tamper else text

    def cue(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str]) -> tuple[OverlayCue | None, NumberCheck]:
        e = moment.evidence
        team = labels.get("team", moment.team_id)
        if moment.kind == "pass_streak" and "pass_streak_passes" in insight.evidence_refs:
            cue = OverlayCue(
                moment_id=moment.moment_id, show_at_seq=moment.window[1], duration_s=8,
                priority="high" if e.get("pass_streak_ended_in_shot") else "normal",
                headline=f"{team}: {_n(e['pass_streak_passes'])}-pass move"[:60],
                metric_label="passes", metric_value=_n(e["pass_streak_passes"]),
            )
        elif moment.kind == "pressing_trap" and "pressing_trap_pressures" in insight.evidence_refs:
            cue = OverlayCue(
                moment_id=moment.moment_id, show_at_seq=moment.window[1], duration_s=8, priority="high",
                headline=f"{team}: pressing trap, ball won high"[:60],
                metric_label="pressures", metric_value=_n(e["pressing_trap_pressures"]),
            )
        else:
            cue = OverlayCue(moment_id=moment.moment_id, show_at_seq=moment.window[1], duration_s=8, priority="low", headline=_shorten(insight.claim, 60))
        cited = {k: e[k] for k in insight.evidence_refs if k in e}
        source = f"{cue.headline} {cue.metric_value or ''}"
        if cue.metric_value is not None:
            cue = cue.model_copy(update={"metric_value": self._text(cue.metric_value, moment.moment_id, "broadcast", "en")})
        headline = self._text(cue.headline, moment.moment_id, "broadcast", "en")
        cue = cue.model_copy(update={"headline": headline[:60]})
        text = f"{cue.headline} {cue.metric_value or ''}"
        check = check_rendering(text, cited, source, moment_id=moment.moment_id, profile_key="broadcast", coverage="all")
        return (cue if check.ok else None), check

    def narrative(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str], profile: FanProfile) -> tuple[FanNarrative | None, NumberCheck]:
        e = moment.evidence
        team = labels.get("team", moment.team_id)
        refs = set(insight.evidence_refs)
        if profile.language == "tr" and moment.kind == "pass_streak" and {"pass_streak_passes", "pass_streak_duration_s"} <= refs:
            text = f"{team} {_n(e['pass_streak_passes'])} pası {_n(e['pass_streak_duration_s'])} saniyede art arda tamamladı."
            if profile.depth == "analyst" and "pass_streak_players" in refs:
                text += f" Bu seride {_n(e['pass_streak_players'])} oyuncu top aldı."
        elif profile.language == "tr" and moment.kind == "pressing_trap" and {"pressing_trap_pressures", "pressing_trap_window_s"} <= refs:
            text = f"{team} {_n(e['pressing_trap_window_s'])} saniyede {_n(e['pressing_trap_pressures'])} kez baskı yaptı ve topu rakip yarı sahada kazandı."
        else:
            text = insight.claim if profile.depth == "casual" else f"{insight.claim} {insight.why_it_matters}"
        cited = {k: e[k] for k in insight.evidence_refs if k in e}
        text = self._text(text, moment.moment_id, profile.key(), profile.language)
        coverage = "all" if profile.depth == "analyst" else "any"
        check = check_rendering(text, cited, insight.claim, moment_id=moment.moment_id, profile_key=profile.key(), lang=profile.language, coverage=coverage)
        narrative = FanNarrative(moment_id=moment.moment_id, profile_key=profile.key(), text=text)
        return (narrative if check.ok else None), check
