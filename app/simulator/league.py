"""The Northshore League: four fictional clubs with fixed 18-player squads.

Every name here is invented. Squads and attributes are static (not seeded per
match) so a player keeps the same identity across every simulated fixture.
"""

from __future__ import annotations

import random
from typing import Literal

from pydantic import BaseModel

LEAGUE_NAME = "Northshore League"

Position = Literal["GK", "DF", "MF", "FW"]


class Player(BaseModel):
    player_id: str
    club_id: str
    name: str
    short_name: str
    shirt: int
    position: Position
    starter: bool
    pace: float
    passing: float
    finishing: float
    pressing: float


class Club(BaseModel):
    club_id: str
    name: str
    short: str
    style: Literal["possession", "pressing", "direct", "balanced"]
    players: list[Player]

    def player(self, player_id: str) -> Player:
        for p in self.players:
            if p.player_id == player_id:
                return p
        raise KeyError(player_id)

    @property
    def starters(self) -> list[Player]:
        return [p for p in self.players if p.starter]

    @property
    def bench(self) -> list[Player]:
        return [p for p in self.players if not p.starter]


_CLUBS = [
    ("vel", "Vellmoor Athletic", "VEL", "possession"),
    ("sal", "Saltreach Mariners", "SAL", "pressing"),
    ("cor", "Corranvale City", "COR", "direct"),
    ("emb", "Embergate United", "EMB", "balanced"),
]

_FIRST_NAMES = [
    "Aren", "Bora", "Cael", "Deniz", "Elio", "Faris", "Galen", "Harun", "Ilan",
    "Joren", "Kerem", "Lio", "Mert", "Nilo", "Oren", "Pelin", "Quill", "Rafe",
    "Selim", "Tarik", "Ulas", "Vance", "Wren", "Yusa", "Zeki", "Alder", "Baris",
    "Corin", "Doruk", "Emir", "Fenn", "Goktan", "Hale", "Ivo", "Jory", "Kaan",
]

_SURNAMES = [
    "Dalvane", "Orrick", "Kestamir", "Brunwell", "Tasyel", "Vornholt", "Ashcombe",
    "Kilavuz", "Merrow", "Sentrel", "Duvanoglu", "Penhallow", "Ravik", "Tolvery",
    "Ekincan", "Halloran-Vey", "Mistrel", "Quorne", "Selvadur", "Brackley-Moon",
    "Ozkandere", "Pellith", "Varnock", "Yildaran", "Corrwyn", "Fenstow", "Gulbeyaz",
    "Hathersage-Lin", "Ivendale", "Jastrow", "Karsuluk", "Lindqvane", "Morvath",
    "Narlitepe", "Oakridge-Vale", "Prenzlow", "Rudhavan", "Sarpkaya-Low", "Thornick",
    "Ulvemark", "Velicandir", "Wyndrel", "Yarbasi", "Zenthorpe", "Albrecane",
    "Beylikdar", "Cindral", "Dornwick", "Erguvanli", "Falkreth", "Gorsemoor",
    "Haskaval", "Isselby", "Junipero-Kade", "Kozanova", "Lattimore-Ash", "Mavikent",
    "Nethercott-Ray", "Ostravel", "Pinarbeck", "Quenby", "Rosswell-Tan", "Solakdere",
    "Tavistrel", "Umbersall", "Vadikoru", "Whitlowe", "Yamacli", "Zorvane",
    "Arkwright-Eze", "Belencik", "Calloway-Dun",
]

# 11 starters in a 4-4-2, then 7 substitutes.
_POSITIONS: list[Position] = (
    ["GK"] + ["DF"] * 4 + ["MF"] * 4 + ["FW"] * 2
    + ["GK", "DF", "DF", "MF", "MF", "FW", "FW"]
)
_SHIRTS = [1, 2, 4, 5, 3, 7, 6, 8, 11, 9, 10, 13, 15, 16, 14, 18, 19, 20]


def _attributes(rng: random.Random, position: Position, style: str) -> dict[str, float]:
    base = {"pace": 0.55, "passing": 0.6, "finishing": 0.3, "pressing": 0.5}
    if position == "GK":
        base = {"pace": 0.35, "passing": 0.5, "finishing": 0.05, "pressing": 0.1}
    elif position == "DF":
        base.update(pace=0.6, passing=0.6, finishing=0.2, pressing=0.6)
    elif position == "MF":
        base.update(pace=0.6, passing=0.72, finishing=0.4, pressing=0.62)
    else:
        base.update(pace=0.72, passing=0.58, finishing=0.7, pressing=0.5)
    if style == "possession":
        base["passing"] += 0.06
    elif style == "pressing":
        base["pressing"] += 0.12
    elif style == "direct":
        base["pace"] += 0.06
        base["finishing"] += 0.04
    return {k: round(min(0.98, max(0.02, v + rng.uniform(-0.12, 0.12))), 2) for k, v in base.items()}


def _build_league() -> dict[str, Club]:
    clubs: dict[str, Club] = {}
    for ci, (club_id, name, short, style) in enumerate(_CLUBS):
        rng = random.Random(1000 + ci)
        players: list[Player] = []
        for pi, position in enumerate(_POSITIONS):
            first = _FIRST_NAMES[(ci * 9 + pi * 5) % len(_FIRST_NAMES)]
            last = _SURNAMES[ci * 18 + pi]
            players.append(Player(
                player_id=f"{club_id}-{_SHIRTS[pi]:02d}",
                club_id=club_id,
                name=f"{first} {last}",
                short_name=f"{first[0]}. {last}",
                shirt=_SHIRTS[pi],
                position=position,
                starter=pi < 11,
                **_attributes(rng, position, style),
            ))
        clubs[club_id] = Club(club_id=club_id, name=name, short=short, style=style, players=players)
    return clubs


LEAGUE: dict[str, Club] = _build_league()

FIXTURES: list[tuple[str, str]] = [
    (h, a) for i, h in enumerate(LEAGUE) for a in list(LEAGUE)[i + 1:]
]


def fixture_for_seed(seed: int) -> tuple[str, str]:
    home, away = FIXTURES[seed % len(FIXTURES)]
    return (away, home) if (seed // len(FIXTURES)) % 2 else (home, away)


def player_by_id(player_id: str) -> Player:
    club_id = player_id.split("-", 1)[0]
    return LEAGUE[club_id].player(player_id)
