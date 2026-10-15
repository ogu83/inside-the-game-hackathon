from app.simulator.model import MatchEvent

MATCH_ID = "m0001-vel-sal"


class Seq:
    """Builds hand-made event sequences with auto-incrementing seq numbers."""

    def __init__(self) -> None:
        self.events: list[MatchEvent] = []

    def add(self, t: int, type_: str, team: str, player: str | None = None, x: float = 50, y: float = 50,
            end_x: float | None = None, end_y: float | None = None, outcome: str | None = None,
            **meta: float | str) -> MatchEvent:
        ev = MatchEvent(match_id=MATCH_ID, seq=len(self.events), minute=t // 60, second=t % 60, type=type_,
                        team_id=team, player_id=player, x=x, y=y, end_x=end_x, end_y=end_y,
                        outcome=outcome, meta=meta)
        self.events.append(ev)
        return ev

    def pass_(self, t: int, team: str, player: str, ok: bool = True, x: float = 40, end_x: float = 50,
              length: float = 15, carry: float = 0, speed: float = 15, receiver: str = "") -> MatchEvent:
        return self.add(t, "pass", team, player, x, 50, end_x, 50, "success" if ok else "fail",
                        pass_length_m=length, carry_m=carry, speed_kmh=speed, receiver_id=receiver)
