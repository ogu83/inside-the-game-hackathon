from app.simulator.models import MatchEvent


class EventFactory:
    """Builds hand-made event sequences with increasing seq and a controllable clock."""

    def __init__(self, match_id: str = "test") -> None:
        self.match_id = match_id
        self.seq = 0
        self.t = 0

    def make(self, type_: str, team: str, *, dt: int = 3, player: int = 1, x: float = 50, end_x: float | None = None,
             outcome: str | None = None) -> MatchEvent:
        self.seq += 1
        self.t += dt
        return MatchEvent(
            match_id=self.match_id, seq=self.seq, minute=self.t // 60, second=self.t % 60, type=type_,
            team_id=team, player_id=f"{team}-{player:02d}", x=x, y=50, end_x=end_x,
            end_y=50 if end_x is not None else None, outcome=outcome,
        )

    def passes(self, team: str, count: int, *, start_x: float = 20, step: float = 5, fail_last: bool = False,
               players: int = 5) -> list[MatchEvent]:
        events = []
        x = start_x
        for i in range(count):
            failed = fail_last and i == count - 1
            events.append(self.make("pass", team, player=i % players + 1, x=x, end_x=x + step,
                                    outcome="fail" if failed else "success"))
            x += step
        return events
