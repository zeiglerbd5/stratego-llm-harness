#!/usr/bin/env python3
"""Play one Game. Walking-skeleton entry point.

    python3 run_game.py --red llama3:latest --blue llama3:latest --variant barrage
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from stratego.adapter import ModelProfile, unload
from stratego.agent import Agent
from stratego.loop import play_game

OLLAMA = "http://127.0.0.1:11434/v1"
OPENROUTER = "https://openrouter.ai/api/v1"
ANTHROPIC = "https://api.anthropic.com"


def profile_for(spec: str, endpoint: str | None,
                max_tokens: int = 4000) -> ModelProfile:
    """'llama3:latest' -> local; 'openrouter/<vendor>/<model>' -> OpenRouter;
    'anthropic/claude-sonnet-5' -> the Claude API directly."""
    # Cloud endpoints manage their own context; context_tokens is Ollama-only.
    if spec.startswith("anthropic/"):
        return ModelProfile(spec.removeprefix("anthropic/"), ANTHROPIC,
                            os.environ.get("ANTHROPIC_API_KEY"),
                            max_tokens=max_tokens, api="anthropic",
                            context_tokens=None)
    if spec.startswith("openrouter/"):
        return ModelProfile(spec.removeprefix("openrouter/"), OPENROUTER,
                            os.environ.get("OPENROUTER_API_KEY"),
                            max_tokens=max_tokens, context_tokens=None)
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
                    choices=["model", "library", "random", "file"],
                    help="who writes the opening setup. Default 'library' gives "
                         "both sides a sound opening so the Game measures play "
                         "rather than setup; 'model' benchmarks setup skill; "
                         "'file' plays Model setups saved by run_deploy.py")
    ap.add_argument("--deployment-file", help="JSON from run_deploy.py (with --deployment file)")
    ap.add_argument("--red-opening", help="library opening for RED "
                    "(default: random, never the same as BLUE's)")
    ap.add_argument("--blue-opening", help="library opening for BLUE "
                    "(default: random, never the same as RED's)")
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
    fixed = None
    if args.deployment == "file":
        if not args.deployment_file:
            ap.error("--deployment file needs --deployment-file")
        fixed = json.loads(Path(args.deployment_file).read_text(encoding="utf-8"))
        fixed["file"] = args.deployment_file
    summary = play_game(red, blue, args.variant, args.move_cap, args.out,
                        args.seed, deployment=args.deployment,
                        openings={"R": args.red_opening, "B": args.blue_opening},
                        fixed=fixed)
    print("\nRESULT:", summary)
    print("Record:", args.out)
    for p in (rp, bp):
        unload(p)


if __name__ == "__main__":
    main()
