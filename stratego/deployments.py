"""The Deployment Library: hand-authored openings of known quality.

Rows run BACK first: rows[0] is the row furthest from the enemy, rows[3] the
front line. Written in board glyphs so a Deployment reads the way the board
renders, and so an entry can double as a few-shot example.

Using these as few-shot examples contaminates a benchmark exactly the way a
Strategy Guide would, so that use rides the same on/off switch.
"""
from __future__ import annotations

import random

from . import rules as R
from .game import validate_deployment

# F Flag  B Bomb  S Spy  M Marshal(10)  9 General  8 Colonel  7 Major
# 6 Captain  5 Lieutenant  4 Sergeant  3 Miner  2 Scout
LIBRARY: dict[str, list[dict]] = {
    "barrage": [
        {"name": "corner-fortress",
         "note": "Flag cornered, Bomb on the file approach, Sergeant on the rank "
                 "approach. Spy tucked behind, Scout forward to probe.",
         "rows": ["F 4 . . . . . . . .",
                  "B S . . . . . . . .",
                  ". 3 . . . . . . . .",
                  ". . 9 . M . 2 . . ."]},
        {"name": "far-corner",
         "note": "Mirror of corner-fortress on the other flank, so a library "
                 "pairing does not always defend the same side.",
         "rows": [". . . . . . . . 4 F",
                  ". . . . . . . . S B",
                  ". . . . . . . 3 . .",
                  ". . . 2 . M . 9 . ."]},
        {"name": "centre-guard",
         "note": "Flag off-corner and harder to guess, but with only three "
                 "approach squares to cover instead of two.",
         "rows": [". . . . F B . . . .",
                  ". . . . 4 . . . . .",
                  ". . 3 . . . S . . .",
                  ". 2 . 9 . . M . . ."]},
    ],
    "classic": [
        {"name": "bombed-left-corner",
         "note": "Flag at a1 walled by Bombs on both approaches. The other four "
                 "Bombs are spread mid-board and front as traps, never stacked. "
                 "Miners distributed so bomb-clearing survives losses.",
         "rows": ["F B 6 8 7 5 4 3 6 3",
                  "B S M 9 6 5 4 3 7 8",
                  "2 3 B 7 5 4 6 5 3 B",
                  "2 2 2 B 4 2 2 B 2 2"]},
        {"name": "bombed-right-corner",
         "note": "Same idea on the right. Two Bombs guard the Flag, two sit "
                 "mid-board and two are seeded in the front line as traps.",
         "rows": ["3 6 8 7 5 4 3 6 B F",
                  "8 7 6 5 4 3 M 9 S B",
                  "B 5 3 7 4 6 5 3 2 B",
                  "2 2 B 2 4 2 2 B 2 2"]},
    ],
}


def _to_deployment(rows: list[str], color: str) -> dict[str, str]:
    numbers = list(R.TERRITORY[color])
    if color == "B":
        numbers = numbers[::-1]          # back row first for both colours
    glyph_to_rank = {v: k for k, v in R.GLYPH.items()}
    dep: dict[str, str] = {}
    for row_str, row_no in zip(rows, numbers):
        cells = row_str.split()
        for c, cell in enumerate(cells):
            if cell != ".":
                dep[R.square(c, row_no)] = glyph_to_rank[cell]
    return dep


def get(variant: str, color: str, name: str | None = None,
        rng: random.Random | None = None) -> tuple[dict[str, str], str]:
    """A validated Deployment from the library, by name or at random."""
    entries = LIBRARY[variant]
    if name:
        entry = next(e for e in entries if e["name"] == name)
    else:
        entry = (rng or random).choice(entries)
    dep = _to_deployment(entry["rows"], color)
    validate_deployment(dep, color, variant)
    return dep, entry["name"]


def names(variant: str) -> list[str]:
    return [e["name"] for e in LIBRARY[variant]]


def validate_library() -> list[str]:
    """Every entry must be legal for both colours. Returns problems found."""
    problems = []
    for variant, entries in LIBRARY.items():
        for e in entries:
            for color in ("R", "B"):
                try:
                    validate_deployment(_to_deployment(e["rows"], color),
                                        color, variant)
                except Exception as ex:
                    problems.append(f"{variant}/{e['name']}/{color}: {ex}")
    return problems
