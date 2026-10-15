"""Print a simulated match as text: python -m app.simulator.run --seed 7 --speed 20"""

from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

from app.simulator.emitter import simulate_match, stream
from app.simulator.export import write_jsonl
from app.simulator.league import LEAGUE, LEAGUE_NAME, player_by_id
from app.simulator.model import MATCH_TEAM_ID, MatchEvent


def _name(player_id: str | None) -> str:
    return player_by_id(player_id).short_name if player_id else ""


def describe(ev: MatchEvent) -> str | None:
    clock = f"{ev.minute:02d}:{ev.second:02d}"
    team = LEAGUE[ev.team_id].short if ev.team_id != MATCH_TEAM_ID else "   "
    who = _name(ev.player_id)
    m = ev.meta
    if ev.type == "pass":
        if ev.outcome == "success":
            text = f"{who} finds {_name(str(m['receiver_id']))} ({m['pass_length_m']:.0f} m)"
        else:
            text = f"{who} gives it away ({m['pass_length_m']:.0f} m pass)"
        if m.get("under_pressure"):
            text += " under pressure"
    elif ev.type == "shot":
        result = "on target" if ev.outcome == "success" else "off target"
        text = f"SHOT {who}, {result}, xG {m['xg']:.2f}, {m['speed_kmh']:.0f} km/h"
    elif ev.type == "goal":
        text = f"GOAL! {who}  [{m['score_home']:.0f}-{m['score_away']:.0f}]"
    elif ev.type == "pressure":
        text = f"{who} closes down ({m['speed_kmh']:.0f} km/h)"
    elif ev.type == "tackle":
        text = f"{who} wins it with a tackle"
    elif ev.type == "interception":
        text = f"{who} intercepts"
    elif ev.type == "possession_change":
        text = f"possession to {LEAGUE[ev.team_id].short} ({m['reason']})"
    elif ev.type == "foul":
        text = f"foul by {who}"
    elif ev.type == "substitution":
        text = f"substitution: {who} on for {_name(str(m['off']))}"
    elif ev.type == "kickoff":
        text = f"kick-off, {who}"
    elif ev.type in ("half_time", "full_time"):
        label = "HALF TIME" if ev.type == "half_time" else "FULL TIME"
        text = f"{label}  [{m['score_home']:.0f}-{m['score_away']:.0f}]"
    else:
        return None
    return f"{clock}  {team}  {text}"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=f"Simulate a {LEAGUE_NAME} match.")
    parser.add_argument("--seed", type=int, default=7)
    parser.add_argument("--speed", type=float, default=20.0, help="match seconds per real second; 0 = instant")
    parser.add_argument("--home", choices=sorted(LEAGUE), default=None)
    parser.add_argument("--away", choices=sorted(LEAGUE), default=None)
    parser.add_argument("--minutes", type=int, default=None, help="stop after this match minute")
    parser.add_argument("--quiet", action="store_true", help="hide passes and pressures")
    parser.add_argument("--export", type=Path, default=None, metavar="PATH",
                        help="write the match as JSONL (e.g. data/match_7.jsonl) and exit")
    args = parser.parse_args(argv)

    events = simulate_match(args.seed, args.home, args.away)
    if args.export:
        n = write_jsonl(events, args.export)
        print(f"wrote {n} events to {args.export}")
        return
    home_id, away_id = events[0].match_id.split("-")[1:]
    print(f"{LEAGUE_NAME}: {LEAGUE[home_id].name} vs {LEAGUE[away_id].name}  ({events[0].match_id})")
    for ev in stream(events, args.speed):
        if args.minutes is not None and ev.minute >= args.minutes:
            break
        if args.quiet and ev.type in ("pass", "pressure"):
            continue
        line = describe(ev)
        if line:
            print(line, flush=True)
    counts = Counter(ev.type for ev in events)
    print(f"\n{len(events)} events: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())))


if __name__ == "__main__":
    main()
