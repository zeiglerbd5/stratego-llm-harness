"""Metrics over a Game Record, including material adjudication.

A Game that hits the move cap is recorded as a draw because that is what
happened. Adjudication is a separate, post-hoc judgement layered on top: it
never rewrites the Game Record.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import rules as R
from .game import GameState, Move
from .rules import VALUE


ADJUDICATION_MARGIN = 3     # points; below this a capped Game is a true draw
SHUFFLE_LOOKBACK = 4


def material(st: GameState) -> dict[str, int]:
    return {c: sum(VALUE[p.rank] for p in st.side(c)) for c in ("R", "B")}


def adjudicate(st: GameState, margin: int = ADJUDICATION_MARGIN) -> tuple[str, str]:
    """Score a capped Game on material. Returns (result, reason)."""
    m = material(st)
    diff = m["R"] - m["B"]
    if abs(diff) < margin:
        return "draw", f"material level ({diff:+d})"
    return ("R" if diff > 0 else "B"), f"material {diff:+d}"


def _replay(recs: list[dict]) -> tuple[GameState, dict[str, str]]:
    start = next(r for r in recs if r["kind"] == "game_start")
    deps = {r["color"]: r["deployment"] for r in recs if r["kind"] == "deployment"}
    st = GameState.from_deployments(deps["R"], deps["B"],
                                    variant=start["variant"],
                                    move_cap=start["move_cap"])
    flags = {c: next(sq for sq, rank in deps[c].items() if rank == "Flag")
             for c in ("R", "B")}
    for r in recs:
        if r["kind"] in ("move", "forfeit"):
            mv = r["move"] if r["kind"] == "move" else r["substituted"]
            frm, to = mv.split("-")
            st.apply(Move(frm, to))
    return st, flags


def _distance(a: str, b: str) -> int:
    ac, ar = R.parse_square(a)
    bc, br = R.parse_square(b)
    return abs(ac - bc) + abs(ar - br)


def analyze(path: str | Path) -> dict:
    recs = [json.loads(l) for l in Path(path).open(encoding="utf-8")]
    start = next(r for r in recs if r["kind"] == "game_start")
    end = next(r for r in recs if r["kind"] == "game_end")
    moves = [r for r in recs if r["kind"] == "move"]
    st, flags = _replay(recs)

    out: dict = {
        "file": str(path),
        "variant": start["variant"],
        "red": start["red"]["model"], "blue": start["blue"]["model"],
        "deployment_source": start.get("deployment_source", "model"),
        "played_result": end["result"], "played_reason": end["reason"],
        "plies": end["plies"],
        "material": material(st),
    }
    out["material_diff"] = out["material"]["R"] - out["material"]["B"]

    if end["result"] == "draw" and end["reason"] == "move_cap":
        res, why = adjudicate(st)
        out["adjudicated_result"], out["adjudicated_reason"] = res, why
    else:
        out["adjudicated_result"], out["adjudicated_reason"] = end["result"], end["reason"]

    per: dict[str, dict] = {}
    for c in ("R", "B"):
        mv = [m for m in moves if m["color"] == c]
        combats = [m for m in mv if m["combat"]]
        won = sum(1 for m in combats if m["combat"]["outcome"] == "defender")
        lost = sum(1 for m in combats if m["combat"]["outcome"] == "attacker")
        traded = sum(1 for m in combats if m["combat"]["outcome"] == "both")

        # Did this side ever go looking for the enemy Flag?
        enemy_flag = flags[R.OPPONENT[c]]
        closest = min((_distance(m["move"].split("-")[1], enemy_flag) for m in mv),
                      default=None)

        # Shuffling: returning a piece to a square it just left.
        recent: dict[str, list[str]] = {}
        shuffles = 0
        for m in mv:
            frm, to = m["move"].split("-")
            hist = recent.get(frm, [])
            if to in hist[-SHUFFLE_LOOKBACK:]:
                shuffles += 1
            recent[to] = hist + [frm]
            recent.pop(frm, None)

        per[c] = {
            "moves": len(mv),
            "piece_types_used": len({m["rank"] for m in mv}),
            "combats_initiated": len(combats),
            "combat_won": won, "combat_lost": lost, "combat_traded": traded,
            "closest_to_enemy_flag": closest,
            "shuffle_moves": shuffles,
            "shuffle_rate": round(shuffles / len(mv), 2) if mv else 0.0,
            "retries": sum(m["retries"] for m in mv),
            "thinking_tokens": sum(m["thinking_tokens"] for m in mv),
            "seconds": round(sum(m["seconds"] for m in mv), 1),
            "reasoning_captured": sum(1 for m in mv if m["reasoning"]),
        }
    out["per_side"] = per
    out["failures"] = end.get("failures", {})
    out["forfeits"] = end.get("forfeits", {})
    out["deployment_substituted"] = end.get("deployment_substituted", [])
    return out


def format_report(a: dict) -> str:
    p = a["per_side"]
    played = a["played_result"]
    adj = a["adjudicated_result"]
    verdict = f"{played} ({a['played_reason']})"
    if adj != played:
        verdict += f"  ->  ADJUDICATED {adj} ({a['adjudicated_reason']})"
    lines = [
        f"{Path(a['file']).name}  [{a['variant']}, deployment={a['deployment_source']}]",
        f"  R={a['red']}   B={a['blue']}",
        f"  result: {verdict}   plies={a['plies']}",
        f"  material: R={a['material']['R']} B={a['material']['B']} "
        f"({a['material_diff']:+d})",
        f"  {'':14s}{'R':>10s}{'B':>10s}",
    ]
    rows = [("moves", "moves"), ("piece types", "piece_types_used"),
            ("combats", "combats_initiated"), ("combat won", "combat_won"),
            ("combat lost", "combat_lost"), ("shuffle rate", "shuffle_rate"),
            ("closest→flag", "closest_to_enemy_flag"), ("retries", "retries"),
            ("think tokens", "thinking_tokens"), ("seconds", "seconds")]
    for label, key in rows:
        lines.append(f"  {label:14s}{str(p['R'][key]):>10s}{str(p['B'][key]):>10s}")
    if a["failures"]:
        lines.append(f"  failures: {a['failures']}  forfeits: {a['forfeits']}")
    if a["deployment_substituted"]:
        lines.append(f"  CONTAMINATED: deployment substituted for "
                     f"{a['deployment_substituted']}")
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    for f in sys.argv[1:]:
        print(format_report(analyze(f)))
        print()
