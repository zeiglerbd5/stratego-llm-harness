#!/usr/bin/env python3
"""Play one Game. Walking-skeleton entry point.

    python3 run_game.py --red llama3:latest --blue llama3:latest --variant barrage
"""
from __future__ import annotations

import argparse
import os

from stratego.adapter import ModelProfile, unload
from stratego.agent import Agent
from stratego.loop import play_game

OLLAMA = "http://127.0.0.1:11434/v1"
OPENROUTER = "https://openrouter.ai/api/v1"


def profile_for(spec: str, endpoint: str | None,
                max_tokens: int = 4000) -> ModelProfile:
    """'llama3:latest' -> local; 'openrouter/anthropic/claude-...' -> cloud."""
    if spec.startswith("openrouter/"):
        return ModelProfile(spec.removeprefix("openrouter/"), OPENROUTER,
                            os.environ.get("OPENROUTER_API_KEY"),
                            max_tokens=max_tokens)
    return ModelProfile(spec, endpoint or OLLAMA, max_tokens=max_tokens)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--red", default="llama3:latest")
    ap.add_argument("--blue", default="llama3:latest")
    ap.add_argument("--red-endpoint")
    ap.add_argument("--blue-endpoint")
    ap.add_argument("--variant", default="barrage", choices=["barrage", "classic"])
    ap.add_argument("--thinking", default="standard",
                    choices=["off", "brief", "standard", "deep"])
    ap.add_argument("--move-assist", default="full",
                    choices=["none", "hints", "full"])
    ap.add_argument("--threat-assist", default="full",
                    choices=["none", "hints", "full"],
                    help="what the enemy can attack next move; mirrors --move-assist")
    ap.add_argument("--strategy-guide", action="store_true",
                    help="append the Strategy Guide (contaminates a benchmark; "
                         "recorded in the Game Record)")
    ap.add_argument("--move-cap", type=int, default=400)
    ap.add_argument("--max-tokens", type=int, default=4000, help="output ceiling per attempt, thinking plus answer, doubled once on exhaustion. Must not bind at the chosen --thinking or the Game is contaminated (ADR-0001): 4000 fits brief on gpt-oss:20b, standard needs ~16000")
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--out", default="records/game.jsonl")
    ap.add_argument("--deployment", default="library",
                    choices=["model", "library", "random"],
                    help="who writes the opening setup. Default 'library' gives "
                         "both sides a sound opening so the Game measures play "
                         "rather than setup; pass 'model' to benchmark setup skill")
    ap.add_argument("--library-entry",
                    help="name a library opening; both sides use it (paired Game)")
    args = ap.parse_args()

    rp = profile_for(args.red, args.red_endpoint, args.max_tokens)
    bp = profile_for(args.blue, args.blue_endpoint, args.max_tokens)
    red = Agent(f"red:{args.red}", rp, "R", args.thinking, args.move_assist,
                args.threat_assist, args.strategy_guide)
    blue = Agent(f"blue:{args.blue}", bp, "B", args.thinking, args.move_assist,
                 args.threat_assist, args.strategy_guide)

    print(f"{args.variant} | {red.name} vs {blue.name} | "
          f"thinking={args.thinking} max_tokens={args.max_tokens} "
          f"move_assist={args.move_assist} "
          f"threat_assist={args.threat_assist} deployment={args.deployment}"
          f"{' +guide' if args.strategy_guide else ''}")
    summary = play_game(red, blue, args.variant, args.move_cap, args.out,
                        args.seed, deployment=args.deployment,
                        library_entry=args.library_entry)
    print("\nRESULT:", summary)
    print("Record:", args.out)
    for p in (rp, bp):
        unload(p)


if __name__ == "__main__":
    main()
