# Matchday Companion

A live co-commentator you can interrupt, and that can't lie: every number it says is checked against the match data before it is spoken.

Entry for the Microsoft + Premier League "Inside the Game: Developer Hackathon" (category: Best Use of Microsoft Foundry). Built on Microsoft Foundry models, Microsoft Agent Framework, Foundry Voice Live and MCP. Everything in this repository is fictional: the Meridian League, its clubs and its players are invented, and any resemblance to real people is accidental.

This README is a work in progress until submission; see [SPEC.md](SPEC.md) for the design and [tasks/plan.md](tasks/plan.md) for the plan.

## Quick start

```
python3 -m venv .venv && . .venv/bin/activate      # Windows: py -3.11 -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
python -m pytest tests/ -q                          # no model calls
python -m uvicorn app.api.main:app --port 8010      # open http://localhost:8010, offline agents unless AGENT_MODE=foundry
```

## Synthetic match dataset

The simulator (`app/simulator`) generates a full 90-minute match of the fictional Meridian League from a seed. Same seed, same match. Three sample matches are committed under `data/` and can be regenerated with `python -m app.simulator.export --seed <seed>`:

| File | Seed | Note |
| --- | --- | --- |
| `data/match_7.jsonl` | 7 | development default |
| `data/match_30.jsonl` | 30 | demo seed: three notable moments in the first five minutes |
| `data/match_42.jsonl` | 42 | |

Each line is one `MatchEvent` as JSON (schema in `app/simulator/models.py`):

| Field | Type | Meaning |
| --- | --- | --- |
| `match_id` | string | `<home>-<away>-<seed>`, e.g. `kby-iva-30` |
| `seq` | int | strictly increasing per match, starts at 1 |
| `minute`, `second` | int | match clock since kickoff; the second half starts at 45:00, no added time |
| `type` | string | `pass`, `shot`, `tackle`, `interception`, `pressure`, `possession_change`, `substitution`, `foul`, `goal`, `kickoff`, `half_time`, `full_time` |
| `team_id` | string | acting club: `kby` Kestrel Bay FC, `iva` Ironvale Athletic |
| `player_id` | string or absent | `<club>-<shirt number>`, e.g. `kby-07`; absent for `half_time` and `full_time` |
| `x`, `y` | float 0-100 | position in the **acting team's frame**: that team always attacks from x = 0 towards x = 100, y = 0 is its right touchline. To draw both teams on one pitch, mirror the away team: `(100 - x, 100 - y)` |
| `end_x`, `end_y` | float or absent | where a pass or shot ended, same frame |
| `outcome` | `success`, `fail` or absent | pass completed or not, shot scored or not, tackle or interception won |
| `meta` | object | per type: `pass_length_m`, `phase` (`build_up`, `transition`), `pressured` (`yes`/`no`), `restart` (`free_kick`) for passes; `xg`, `speed_kmh`, `distance_m` for shots; `player_off`, `player_on`, `position` for substitutions; `home_goals`, `away_goals` on `half_time` and `full_time` |

Notes for analysts: possession is computed as pass-attempt share (the common broadcast method), pitch dimensions are 105 m by 68 m, and `pressure` events are emitted by the defending club at the ball carrier's mirrored position. No real match data was used; the event schema is our own and the data is generated.

## Licence of the data

Generated, fictional, and part of this repository's submission. No third-party data.
