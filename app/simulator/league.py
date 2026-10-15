"""The fictional Meridian League. Every club and player name here is invented."""

from dataclasses import dataclass
from typing import Literal

Position = Literal["GK", "RB", "CB", "LB", "DM", "CM", "RW", "LW", "ST"]

NOMINAL_X: dict[str, float] = {
    "GK": 5, "CB": 22, "RB": 32, "LB": 32, "DM": 40, "CM": 52, "RW": 70, "LW": 70, "ST": 80,
}
NOMINAL_Y: dict[str, float] = {
    "GK": 50, "CB": 50, "RB": 15, "LB": 85, "DM": 50, "CM": 50, "RW": 15, "LW": 85, "ST": 50,
}
FORMATION: tuple[Position, ...] = ("GK", "RB", "CB", "CB", "LB", "DM", "CM", "CM", "RW", "ST", "LW")


@dataclass(frozen=True)
class Player:
    id: str
    name: str
    number: int
    position: Position


@dataclass(frozen=True)
class Club:
    id: str
    name: str
    short: str
    players: tuple[Player, ...]

    @property
    def starters(self) -> tuple[Player, ...]:
        return self.players[:11]

    @property
    def subs(self) -> tuple[Player, ...]:
        return self.players[11:]


def _club(club_id: str, name: str, short: str, names: list[str], sub_positions: list[Position]) -> Club:
    positions = list(FORMATION) + sub_positions
    numbers = [1, 2, 4, 5, 3, 6, 8, 10, 7, 9, 11, 12, 14, 17]
    players = tuple(
        Player(f"{club_id}-{numbers[i]:02d}", names[i], numbers[i], positions[i]) for i in range(len(names))
    )
    return Club(club_id, name, short, players)


LEAGUE_NAME = "Meridian League"

CLUBS: dict[str, Club] = {
    club.id: club
    for club in (
        _club(
            "kby", "Kestrel Bay FC", "Kestrel Bay",
            ["Ollie Marsh", "Tomas Vire", "Caden Holloway", "Rafe Okonjo", "Milo Strand", "Ezra Quill",
             "Bram Teller", "Jonah Fenwick", "Luca Brightwater", "Sami Kerrow", "Dax Penhallow",
             "Finn Ashby", "Theo Varga", "Nico Larkspur"],
            ["GK", "CM", "ST"],
        ),
        _club(
            "iva", "Ironvale Athletic", "Ironvale",
            ["Aurel Stone", "Kit Davanne", "Hugo Merrow", "Ilan Coste", "Benji Arkwright", "Remy Tallis",
             "Otto Brennick", "Silas Vane", "Jory Calloway", "Malik Orrin", "Zeno Hartigan",
             "Pim Rookwood", "Abel Thorne", "Cass Delmar"],
            ["GK", "CB", "RW"],
        ),
    )
}

PLAYERS: dict[str, Player] = {p.id: p for club in CLUBS.values() for p in club.players}


def club_of(player_id: str) -> Club:
    return CLUBS[player_id.split("-")[0]]
