"""Print a simulated match as text.

    python -m app.simulator.run --seed 7 --speed 20     # 20x real time
    python -m app.simulator.run --seed 7 --speed 0      # instant
"""

import argparse
import time

from app.simulator.engine import simulate
from app.simulator.league import CLUBS, PLAYERS
from app.simulator.models import MatchEvent


def describe(event: MatchEvent) -> str:
    club = CLUBS[event.team_id].short
    who = PLAYERS[event.player_id].name if event.player_id else ""
    clock = f"{event.minute:02d}:{event.second:02d}"
    match event.type:
        case "pass":
            verdict = "" if event.outcome == "success" else "  (misplaced)"
            return f"{clock} {club:<12} {who} plays it {event.meta.get('pass_length_m')} m{verdict}"
        case "shot":
            return f"{clock} {club:<12} SHOT {who}, {event.meta.get('distance_m')} m out, xG {event.meta.get('xg')}"
        case "goal":
            return f"{clock} {club:<12} GOAL! {who}"
        case "pressure":
            return f"{clock} {club:<12} {who} presses"
        case "tackle":
            return f"{clock} {club:<12} {who} wins it with a tackle"
        case "interception":
            return f"{clock} {club:<12} {who} intercepts"
        case "possession_change":
            return f"{clock} {club:<12} ball won ({event.meta.get('phase')})"
        case "foul":
            return f"{clock} {club:<12} foul by {who}"
        case "kickoff":
            return f"{clock} {club:<12} kick-off"
        case "half_time" | "full_time":
            label = "HALF TIME" if event.type == "half_time" else "FULL TIME"
            return f"{clock} {label} {int(event.meta['home_goals'])}-{int(event.meta['away_goals'])}"
    return f"{clock} {club:<12} {event.type}"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--speed", type=float, default=20, help="x real time; 0 prints instantly")
    parser.add_argument("--minutes", type=int, default=90)
    parser.add_argument("--home", default="kby")
    parser.add_argument("--away", default="iva")
    args = parser.parse_args()

    events = simulate(args.seed, args.home, args.away, args.minutes)
    previous = 0
    for event in events:
        if args.speed > 0:
            time.sleep(max(0, event.t - previous) / args.speed)
        previous = event.t
        print(describe(event), flush=True)


if __name__ == "__main__":
    main()
