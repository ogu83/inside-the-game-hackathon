"""Human-readable names for a moment, so agents can write text without ever seeing ids."""

from app.ledger.models import CandidateMoment
from app.simulator.league import CLUBS, LEAGUE_NAME, PLAYERS


def match_teams(moment: CandidateMoment) -> tuple[str, str] | None:
    """Home and away ids, read from the `home-away-seed` match id prefix the simulator uses."""
    parts = moment.moment_id.split("-")
    if len(parts) >= 2 and parts[0] in CLUBS and parts[1] in CLUBS:
        return parts[0], parts[1]
    return None


def moment_labels(moment: CandidateMoment, teams: tuple[str, str] | None = None) -> dict[str, str]:
    teams = teams or match_teams(moment)
    team = CLUBS.get(moment.team_id)
    opponent_id = next((t for t in (teams or ()) if t != moment.team_id), None)
    opponent = CLUBS.get(opponent_id) if opponent_id else None
    labels = {
        "league": LEAGUE_NAME,
        "team": team.short if team else moment.team_id,
        "team_full": team.name if team else moment.team_id,
        "opponent": opponent.short if opponent else "the opposition",
        "kind": moment.kind.replace("_", " "),
    }
    if moment.top_player_id and moment.top_player_id in PLAYERS:
        labels["top_player"] = PLAYERS[moment.top_player_id].name
    return labels


def profile_labels(labels: dict[str, str], club_id: str | None, player_id: str | None) -> dict[str, str]:
    """Labels plus the fan's club and player names, for one profile's rendering."""
    extra = dict(labels)
    if club_id and club_id in CLUBS:
        extra["fan_club"] = CLUBS[club_id].short
    if player_id and player_id in PLAYERS:
        extra["fan_player"] = PLAYERS[player_id].name
    return extra
