from typing import Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "pass", "shot", "tackle", "interception", "pressure",
    "possession_change", "substitution", "foul", "goal",
    "kickoff", "half_time", "full_time",
]


class MatchEvent(BaseModel):
    """One match event. Coordinates are 0-100 in the acting team's frame (it attacks left to right)."""

    match_id: str
    seq: int
    minute: int
    second: int
    type: EventType
    team_id: str
    player_id: str | None = None
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    end_x: float | None = None
    end_y: float | None = None
    outcome: Literal["success", "fail"] | None = None
    meta: dict[str, float | str] = Field(default_factory=dict)

    @property
    def t(self) -> int:
        """Match time in seconds since kickoff."""
        return self.minute * 60 + self.second
