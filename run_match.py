#!/usr/bin/env python3
"""Play a Match: N paired Games (colours swapped) between two Models.

    python3 run_match.py --a gpt-oss:20b --b gpt-oss:20b --pairs 3
"""
from __future__ import annotations

import argparse

from run_game import profile_for
from stratego.adapter import unload
from stratego.match import format_report, play_match


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--a", required=True)
    ap.add_argument("--b", required=True)
    ap.add_argument("--a-endpoint")
    ap.add_argument("--b-endpoint")
    ap.add_argument("--pairs", type=int, default=3)
    ap.add_argument("--variant", default="barrage", choices=["barrage", "classic"])
    ap.add_argument("--thinking", default="brief", choices=["off", "brief", "standard", "deep"])
    ap.add_argument("--move-cap", type=int, default=60)
    ap.add_argument("--move-assist", default="full", choices=["none", "hints", "full"])
    ap.add_argument("--threat-assist", default="full", choices=["none", "hints", "full"])
    ap.add_argument("--deployment", default="library", choices=["model", "library"])
    ap.add_argument("--seed", type=int, default=100)
    ap.add_argument("--out", default="records/match")
    args = ap.parse_args()

    pa = profile_for(args.a, args.a_endpoint)
    pb = profile_for(args.b, args.b_endpoint)
    report = play_match(pa, pb, args.pairs, args.variant, args.thinking,
                        args.move_cap, args.out, args.seed, args.move_assist,
                        args.threat_assist, args.deployment)
    print("\n" + format_report(report, pa.name, pb.name))
    print(f"\nRecords + match.json in {args.out}/")
    for p in (pa, pb):
        unload(p)


if __name__ == "__main__":
    main()
