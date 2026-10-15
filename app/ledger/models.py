from pydantic import BaseModel


class CandidateMoment(BaseModel):
    moment_id: str
    window: tuple[int, int]       # seq range the moment covers
    kind: str                     # e.g. "pressing_trap", "momentum_shift", "pass_streak"
    team_id: str                  # team the moment is about
    minute: int                   # match minute when the moment ended
    evidence: dict[str, float]    # ledger numbers the claim may cite
    top_player_id: str | None = None  # most involved player; evidence carries top_player_* numbers about them
