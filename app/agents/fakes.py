"""Model-free agents: deterministic templates for offline mode, and scripted doubles for tests.

Offline mode is what `docker compose` runs without Azure and what the API falls back to when no
model is configured. Every template still passes through the same Fact-Checker gates.
"""

from app.agents.models import FanProfile, Insight, WordingVerdict
from app.agents.producer import CueDraft
from app.ledger.models import CandidateMoment


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


class TemplateRenderer:
    """Deterministic renderer for offline mode: fixed sentences filled from cited evidence, per depth and language."""

    async def cue(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str], feedback: list[str]) -> CueDraft:
        e = moment.evidence
        team = labels.get("team", moment.team_id)
        refs = set(insight.evidence_refs)
        if moment.kind == "pass_streak" and "pass_streak_passes" in refs:
            return CueDraft(headline=f"{team}: {_n(e['pass_streak_passes'])}-pass move"[:60], metric_label="passes", metric_value=_n(e["pass_streak_passes"]),
                            priority="high" if e.get("pass_streak_ended_in_shot") else "normal")
        if moment.kind == "pressing_trap" and "pressing_trap_pressures" in refs:
            return CueDraft(headline=f"{team}: pressing trap, ball won high"[:60], metric_label="pressures", metric_value=_n(e["pressing_trap_pressures"]), priority="high")
        return CueDraft(headline=_shorten(insight.claim, 60), priority="low")

    async def narrative(self, insight: Insight, moment: CandidateMoment, labels: dict[str, str], profile: FanProfile, feedback: list[str]) -> str:
        e = moment.evidence
        team = labels.get("team", moment.team_id)
        refs = set(insight.evidence_refs)
        fan_player = labels.get("fan_player") if profile.player_id and profile.player_id == moment.top_player_id else None
        if profile.language == "tr":
            if moment.kind == "pass_streak" and {"pass_streak_passes", "pass_streak_duration_s"} <= refs:
                text = f"{team} {_n(e['pass_streak_passes'])} pası {_n(e['pass_streak_duration_s'])} saniyede art arda tamamladı."
                if profile.depth == "analyst":
                    if "pass_streak_players" in refs:
                        text += f" Bu seride {_n(e['pass_streak_players'])} oyuncu top aldı."
                    if "top_player_passes" in refs and labels.get("top_player"):
                        text += f" {labels['top_player']} {_n(e['top_player_passes'])} pasla serinin merkezindeydi."
                elif fan_player and "top_player_passes" in refs:
                    text += f" Senin oyuncun {fan_player} {_n(e['top_player_passes'])} pas verdi."
                return text
            if moment.kind == "pressing_trap" and {"pressing_trap_pressures", "pressing_trap_window_s"} <= refs:
                text = f"{team} {_n(e['pressing_trap_window_s'])} saniyede {_n(e['pressing_trap_pressures'])} kez baskı yaptı ve topu rakip yarı sahada kazandı."
                if profile.depth == "analyst" and "pressing_trap_regain_distance_to_goal_m" in refs:
                    text += f" Top kaleye {_n(e['pressing_trap_regain_distance_to_goal_m'])} metre mesafede kazanıldı."
                return text
            return insight.claim
        text = insight.claim if profile.depth == "casual" else f"{insight.claim} {insight.why_it_matters}"
        if fan_player and "top_player_passes" in refs and profile.depth == "casual":
            text += f" Your player {fan_player} made {_n(e['top_player_passes'])} of those passes."
        return text
