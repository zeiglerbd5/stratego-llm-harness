"""A Match: paired Games between two Agents that survive setup luck.

Each pair plays one opening twice with colours swapped. Results are scored per
Model (pooling both colours) and per colour (to expose orientation bias).
"""
from __future__ import annotations

import json
from pathlib import Path

from . import deployments as lib
from .adapter import AdapterError, ModelProfile
from .agent import Agent
from .loop import play_game
from .metrics import analyze


def play_match(model_a: ModelProfile, model_b: ModelProfile, pairs: int,
               variant: str = "barrage", thinking: str = "brief",
               move_cap: int = 60, out_dir: str | Path = "records/match",
               base_seed: int = 100, move_assist: str = "full",
               threat_assist: str = "full", deployment: str = "library",
               verbose: bool = True) -> dict:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    openings = lib.names(variant)
    games: list[dict] = []

    halted = False
    for i in range(pairs):
        if halted:
            break
        entry = openings[i % len(openings)] if deployment == "library" else None
        seed = base_seed + i
        for swap in (False, True):
            red_m, blue_m = (model_b, model_a) if swap else (model_a, model_b)
            red = Agent(f"red:{red_m.name}", red_m, "R", thinking, move_assist, threat_assist)
            blue = Agent(f"blue:{blue_m.name}", blue_m, "B", thinking, move_assist, threat_assist)
            tag = f"p{i}{'b' if swap else 'a'}"
            path = out_dir / f"{tag}.jsonl"
            done = _completed(path)
            if done:
                if verbose:
                    print(f"\n=== pair {i} game {'b' if swap else 'a'}: already "
                          f"complete, resuming past it")
                summary = done
            else:
                if verbose:
                    print(f"\n=== pair {i} game {'b' if swap else 'a'}: "
                          f"R={red_m.name} B={blue_m.name} opening={entry} seed={seed}")
                try:
                    summary = play_game(red, blue, variant, move_cap, path, seed,
                                        verbose=verbose, deployment=deployment,
                                        library_entry=entry)
                except AdapterError as e:
                    # The Model server is gone. Keep what finished; a rerun
                    # with the same --out resumes from here.
                    print(f"\nMATCH HALTED at {tag}: {e}")
                    print(f"Completed games are kept; rerun with --out {out_dir} to resume.")
                    halted = True
                    break
            a = analyze(path)
            games.append({
                "tag": tag, "file": str(path), "seed": seed, "opening": entry,
                "red_model": red_m.name, "blue_model": blue_m.name,
                "played": summary["result"], "adjudicated": summary["adjudicated_result"],
                "adjudicated_reason": summary["adjudicated_reason"],
                "material": summary["material"], "plies": summary["plies"],
                "per_side": a["per_side"], "failures": summary["failures"],
            })
            if verbose:
                print(f"    -> {summary['result']} ({summary['reason']}), "
                      f"adjudicated {summary['adjudicated_result']} "
                      f"({summary['adjudicated_reason']})")

    report = aggregate(games, model_a.name, model_b.name) if games else \
        {"by_model": {}, "by_color": {}, "means": {}, "n_games": 0}
    (out_dir / "match.json").write_text(json.dumps(
        {"model_a": model_a.name, "model_b": model_b.name, "variant": variant,
         "thinking": thinking, "move_cap": move_cap, "games": games,
         "report": report}, indent=1))
    return report


def _completed(path: Path) -> dict | None:
    """The game_end summary if this Game Record finished, else None."""
    if not path.exists():
        return None
    last = None
    for line in path.open(encoding="utf-8"):
        last = json.loads(line)
    if last and last.get("kind") == "game_end":
        return {k: last[k] for k in ("result", "reason", "plies", "material",
                                     "adjudicated_result", "adjudicated_reason",
                                     "failures")}
    return None


def aggregate(games: list[dict], a: str, b: str) -> dict:
    """Scores by ROLE (a/b), not by model name: in self-play both names are
    identical and keying by name double-counts every game."""
    by_model = {"a": {"wins": 0, "losses": 0, "draws": 0, "games": 0},
                "b": {"wins": 0, "losses": 0, "draws": 0, "games": 0}}
    by_color = {"R": 0, "B": 0, "draw": 0}
    pooled: dict[str, dict[str, list]] = {"a": {}, "b": {}}
    rejections: dict[str, dict[str, int]] = {"a": {}, "b": {}}

    for g in games:
        res = g["adjudicated"]
        by_color[res if res in ("R", "B") else "draw"] += 1
        # tag ends in 'a' when a is Red, 'b' when a is Blue (colours swapped)
        a_is_red = g["tag"].endswith("a")
        roles = (("R", "a" if a_is_red else "b"), ("B", "b" if a_is_red else "a"))
        for color, model in roles:
            m = by_model[model]
            m["games"] += 1
            if res == "draw":
                m["draws"] += 1
            elif res == color:
                m["wins"] += 1
            else:
                m["losses"] += 1
            for k, v in g["per_side"][color].items():
                if isinstance(v, (int, float)) and v is not None:
                    pooled[model].setdefault(k, []).append(v)
            for k, v in g["per_side"][color].get("rejections", {}).items():
                rejections[model][k] = rejections[model].get(k, 0) + v

    means = {m: {k: round(sum(v) / len(v), 2) for k, v in stats.items() if v}
             for m, stats in pooled.items()}
    return {"by_model": by_model, "by_color": by_color, "means": means,
            "rejections": rejections,
            "n_games": len(games), "names": {"a": a, "b": b}}


def format_report(r: dict, a: str, b: str) -> str:
    if not r.get("n_games"):
        return f"MATCH  {a}  vs  {b}   no completed games"
    lines = [f"MATCH  {a} (a)  vs  {b} (b)   ({r['n_games']} games, adjudicated)"]
    for role, name in (("a", a), ("b", b)):
        s = r["by_model"][role]
        lines.append(f"  {role}: {name:17s} W {s['wins']}  L {s['losses']}  D {s['draws']}"
                     f"   ({s['games']} games)")
    c = r["by_color"]
    lines.append(f"  by colour:           RED {c['R']}  BLUE {c['B']}  draw {c['draw']}")
    lines.append("")
    keys = [("shuffle_rate", "shuffle"), ("closest_to_enemy_flag", "closest→flag"),
            ("combats_initiated", "combats"), ("combat_won", "won"),
            ("combat_lost", "lost"), ("retries", "retries"),
            ("thinking_tokens", "think tok"), ("completion_tokens", "completion tok"),
            ("seconds", "seconds")]
    lines.append(f"  {'mean per game':18s}{'a: '+a[:12]:>16s}{'b: '+b[:12]:>16s}")
    for k, label in keys:
        va = r["means"]["a"].get(k, "-"); vb = r["means"]["b"].get(k, "-")
        lines.append(f"  {label:18s}{str(va):>16s}{str(vb):>16s}")
    rej = r.get("rejections", {})
    if any(rej.values()):
        lines.append("")
        for role in ("a", "b"):
            kinds = ", ".join(f"{k} {v}" for k, v in sorted(rej.get(role, {}).items()))
            lines.append(f"  rejections {role}:      {kinds or 'none'}")
    return "\n".join(lines)
