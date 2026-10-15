"""Event schema shared by the simulator and the ledger (SPEC.md, simulator -> ledger).

Coordinates are 0-100 on both axes and always expressed from the acting team's
point of view, attacking left to right (x=100 is the opponent's goal line).
Match-level events (half_time, full_time) use team_id "match".
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "pass", "shot", "tackle", "interception", "pressure",
    "possession_change", "substitution", "foul", "goal",
    "kickoff", "half_time", "full_time",
]

MATCH_TEAM_ID = "match"

PITCH_LENGTH_M = 105.0
PITCH_WIDTH_M = 68.0


class MatchEvent(BaseModel):
    match_id: str
    seq: int = Field(ge=0)
    minute: int = Field(ge=0)
    second: int = Field(ge=0, le=59)
    type: EventType
    team_id: str
    player_id: str | None
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    end_x: float | None = Field(default=None, ge=0, le=100)
    end_y: float | None = Field(default=None, ge=0, le=100)
    outcome: Literal["success", "fail"] | None = None
    meta: dict[str, float | str] = Field(default_factory=dict)

    @property
    def clock_s(self) -> int:
        return self.minute * 60 + self.second
