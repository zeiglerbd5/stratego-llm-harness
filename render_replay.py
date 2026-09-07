#!/usr/bin/env python3
"""Render a Game Record as a self-contained HTML replay.

    python3 render_replay.py records/classic-sonnet5-vs-terra/g1.jsonl
    python3 render_replay.py records/match-sonnet5-vs-terra-standard/p0a.jsonl \
        --title "Corner Fortress Falls" --out replays/p0a.html

The page needs no server and no network: open it in a browser. It steps
through every Move with the Rationale beside the board, shows what each side
had revealed, and can render the board as either side actually saw it.
"""
from __future__ import annotations

import argparse
import html
import json
from pathlib import Path

TEMPLATE = Path(__file__).parent / "stratego" / "replay_template.html"

SHORT = {"claude-sonnet-5": "Sonnet 5", "claude-opus-5": "Opus 5", "claude-haiku-4-5": "Haiku 4.5"}


def short_name(model: str) -> str:
    """'openai/gpt-5.6-terra' -> 'gpt-5.6-terra'; known Claude ids get their product name."""
    if model in SHORT:
        return SHORT[model]
    return model.split("/")[-1]


def load(path: Path) -> dict:
    recs = [json.loads(line) for line in path.open(encoding="utf-8") if line.strip()]
    start = next(r for r in recs if r["kind"] == "game_start")
    end = next((r for r in recs if r["kind"] == "game_end"), None)
    if end is None:
        raise SystemExit(f"{path}: no game_end - the Game is unfinished or the record is truncated")
    deps = {r["color"]: r["deployment"] for r in recs if r["kind"] == "deployment"}
    moves = [{k: r.get(k) for k in ("ply", "color", "move", "rank", "combat", "rationale",
                                     "thinking_tokens", "seconds")}
             for r in recs if r["kind"] == "move"]
    return {"start": start, "end": end, "deps": deps, "moves": moves}


def setup_text(start: dict, names: dict[str, str]) -> tuple[str, str]:
    """(plain, html) descriptions of where the Deployments came from."""
    src = start.get("deployment_source", "model")
    if src == "library" and start.get("openings"):
        o = start["openings"]
        plain = f"openings Red {o['R']}, Blue {o['B']}"
        rich = (f'<span class="side R">{html.escape(names["R"])}</span> plays {html.escape(o["R"])}; '
                f'<span class="side B">{html.escape(names["B"])}</span> plays {html.escape(o["B"])}.')
    elif src == "file":
        plain = f"setups written by each Model and reviewed before play ({start.get('deployment_file')})"
        rich = (f'<span class="side R">{html.escape(names["R"])}</span> and '
                f'<span class="side B">{html.escape(names["B"])}</span> each wrote their own setup, reviewed before play.')
    elif src == "random":
        plain, rich = "random Deployments", "Both sides were given random Deployments."
    else:
        plain = "setups written by each Model"
        rich = (f'<span class="side R">{html.escape(names["R"])}</span> and '
                f'<span class="side B">{html.escape(names["B"])}</span> each wrote their own setup.')
    return plain, rich


def default_subline(g: dict, names: dict[str, str]) -> str:
    end, start = g["end"], g["start"]
    winner = {"R": names["R"], "B": names["B"]}.get(end["result"], "Nobody")
    how = {"flag_captured": "by capturing the Flag", "no_legal_moves": "by leaving the other side with no legal Move",
           "move_cap": "at the move cap", "forfeit_limit": "after the other side forfeited five times"}.get(end["reason"], end["reason"])
    outcome = (f"{winner} wins {how} at ply {end['plies']}." if end["result"] in ("R", "B")
               else f"Drawn {how} at ply {end['plies']}, material {end['material']['R']} to {end['material']['B']}.")
    variant = start["variant"].capitalize()
    n = {"barrage": 8, "classic": 40}[start["variant"]]
    return (f'<span class="side R">Red, {html.escape(names["R"])}</span> against '
            f'<span class="side B">Blue, {html.escape(names["B"])}</span>, {variant}, {n} pieces a side, '
            f'thinking at {html.escape(start["red"]["thinking"])}. {html.escape(outcome)} '
            f"The rationales are the models' own words, verbatim.")


def render(path: Path, title: str | None, subline: str | None) -> str:
    g = load(path)
    start, end = g["start"], g["end"]
    names = {"R": short_name(start["red"]["model"]), "B": short_name(start["blue"]["model"])}
    plain, rich = setup_text(start, names)
    title = title or f"{names['R']} vs {names['B']}, {start['variant'].capitalize()}"
    data = {
        "meta": {"red": names["R"], "blue": names["B"],
                 "red_model": start["red"]["model"], "blue_model": start["blue"]["model"],
                 "record": str(path), "setup_text": plain, "setup_html": rich,
                 "prompt_version": start.get("prompt_version"), "thinking": start["red"]["thinking"],
                 "move_cap": start["move_cap"], "result": end["result"], "reason": end["reason"],
                 "plies": end["plies"], "material": end["material"]},
        "deploy": g["deps"], "moves": g["moves"],
    }
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    page = TEMPLATE.read_text(encoding="utf-8")
    eyebrow = f"Stratego · {start['variant'].capitalize()} · {names['R']} vs {names['B']}"
    return (page.replace("__TITLE__", html.escape(title))
                .replace("__EYEBROW__", html.escape(eyebrow))
                .replace("__SUBLINE__", subline or default_subline(g, names))
                .replace("__GAME_DATA__", payload))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("record", help="a Game Record (.jsonl)")
    ap.add_argument("--out", help="output .html (default: next to the record)")
    ap.add_argument("--title", help="page name (default: '<Red> vs <Blue>, <Variant>')")
    ap.add_argument("--subline", help="HTML for the paragraph under the title (default: generated)")
    args = ap.parse_args()
    src = Path(args.record)
    out = Path(args.out) if args.out else src.with_suffix(".html")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(src, args.title, args.subline), encoding="utf-8")
    print(f"wrote {out} ({out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
