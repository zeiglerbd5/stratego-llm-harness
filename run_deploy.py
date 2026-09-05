#!/usr/bin/env python3
"""Ask each Model for its Deployment, show both boards, and save them, so a
Game can be played from setups a human has looked at before any Move is paid
for.

    python3 run_deploy.py --red anthropic/claude-sonnet-5 \
        --blue openrouter/openai/gpt-5.6-terra --variant classic \
        --out records/classic-1.deploy.json
    python3 run_game.py --red ... --blue ... --variant classic \
        --deployment file --deployment-file records/classic-1.deploy.json
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from run_game import profile_for
from stratego import rules as R
from stratego.adapter import unload
from stratego.agent import Agent


def board_rows(dep: dict[str, str], color: str) -> list[str]:
    """The four home rows as glyphs, in board orientation (top row first)."""
    rows = sorted(R.TERRITORY[color], reverse=True)
    out = []
    for r in rows:
        cells = [R.GLYPH.get(dep.get(R.square(c, r), ""), ".") for c in range(10)]
        out.append(f"{r:>2} " + " ".join(cells))
    return out


def sanity(dep: dict[str, str], color: str) -> list[str]:
    """Facts a human checks before trusting a setup. Informational only."""
    back = R.TERRITORY[color][0] if color == "R" else R.TERRITORY[color][-1]
    front = R.TERRITORY[color][-1] if color == "R" else R.TERRITORY[color][0]
    by_rank: dict[str, list[str]] = {}
    for sq, rank in dep.items():
        by_rank.setdefault(rank, []).append(sq)
    notes = []
    flag = by_rank.get("Flag", ["?"])[0]
    fc, fr = R.parse_square(flag)
    neighbours = [R.square(fc + dc, fr + dr) for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1))
                  if R.on_board(fc + dc, fr + dr)]
    open_nb = [n for n in neighbours if R.parse_square(n)[1] in R.TERRITORY[color]
               or R.parse_square(n)[1] not in R.TERRITORY[color]]
    bombs_nb = [n for n in neighbours if dep.get(n) == "Bomb"]
    notes.append(f"Flag {flag}" + (" on the back row" if fr == back else " NOT on the back row")
                 + f"; {len(bombs_nb)} of its {len(open_nb)} neighbours are Bombs")
    front_of = lambda rank: [s for s in by_rank.get(rank, []) if R.parse_square(s)[1] == front]
    notes.append(f"front row: {len(front_of('Scout'))} Scouts, {len(front_of('Miner'))} Miners, "
                 f"{len(front_of('Bomb'))} Bombs" + (", the Marshal" if front_of("Marshal") else "")
                 + (", the Spy" if front_of("Spy") else "") + (", the FLAG" if front_of("Flag") else ""))
    spy = by_rank.get("Spy", [None])[0]
    if spy:
        sc, sr = R.parse_square(spy)
        near = [dep.get(R.square(sc + dc, sr + dr)) for dc, dr in ((1, 0), (-1, 0), (0, 1), (0, -1))
                if R.on_board(sc + dc, sr + dr)]
        notes.append(f"Spy {spy}" + (" beside the " + "/".join(x for x in near if x in ("Marshal", "General"))
                                     if any(x in ("Marshal", "General") for x in near) else " not beside Marshal or General"))
    return notes


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--red", required=True)
    ap.add_argument("--blue", required=True)
    ap.add_argument("--variant", default="classic", choices=["barrage", "classic"])
    ap.add_argument("--thinking", default="standard", choices=["off", "brief", "standard", "deep"])
    ap.add_argument("--max-tokens", type=int, default=16000)
    ap.add_argument("--out", required=True, help="JSON file for run_game.py --deployment file")
    args = ap.parse_args()

    saved: dict = {"variant": args.variant, "thinking": args.thinking}
    for color, spec in (("R", args.red), ("B", args.blue)):
        prof = profile_for(spec, None, args.max_tokens)
        ag = Agent(f"{'red' if color == 'R' else 'blue'}:{spec}", prof, color, args.thinking)
        dep, why, attempts = ag.deploy(args.variant)
        name = "RED" if color == "R" else "BLUE"
        if not dep:
            print(f"\n{name} {spec}: no valid Deployment after {len(attempts)} attempts:")
            for a in attempts:
                print("   ", a.get("error"))
            saved[color] = {"agent": ag.name, "model": prof.name, "deployment": None,
                            "rationale": why, "attempts": attempts}
            continue
        print(f"\n{name} {spec}  ({len(attempts)} attempt{'s' if len(attempts) != 1 else ''}, "
              f"{sum(a['thinking_tokens'] for a in attempts)} thinking tokens)")
        print("    a b c d e f g h i j")
        print("\n".join(board_rows(dep, color)))
        for n in sanity(dep, color):
            print("  -", n)
        print("  rationale:", why[:400])
        saved[color] = {"agent": ag.name, "model": prof.name, "deployment": dep,
                        "rationale": why, "attempts": attempts}
        unload(prof)

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(saved, indent=1, ensure_ascii=False), encoding="utf-8")
    ok = all(saved[c]["deployment"] for c in ("R", "B"))
    print(f"\nsaved {args.out}" + ("" if ok else "  (INCOMPLETE: a side has no Deployment)"))


if __name__ == "__main__":
    main()
