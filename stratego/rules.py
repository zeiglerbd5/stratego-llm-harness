"""Stratego rules: ranks, variants, board geometry, and combat resolution.

Contains no game state. Everything here is a fact about Stratego itself.
"""
from __future__ import annotations

COLS = "abcdefghij"
ROWS = range(1, 11)

# Rank order. Flag and Bomb have no rank and never move.
RANK = {
    "Spy": 1, "Scout": 2, "Miner": 3, "Sergeant": 4, "Lieutenant": 5,
    "Captain": 6, "Major": 7, "Colonel": 8, "General": 9, "Marshal": 10,
}
IMMOBILE = ("Flag", "Bomb")
ALL_RANKS = tuple(RANK) + IMMOBILE

# Single-character board glyphs. Unambiguous: digits are ranks 2-9,
# M=Marshal(10), S=Spy(1), B=Bomb, F=Flag.
GLYPH = {
    "Flag": "F", "Bomb": "B", "Spy": "S", "Scout": "2", "Miner": "3",
    "Sergeant": "4", "Lieutenant": "5", "Captain": "6", "Major": "7",
    "Colonel": "8", "General": "9", "Marshal": "M",
}

LAKES = frozenset(
    f"{c}{r}" for c in "cd" for r in (5, 6)
) | frozenset(
    f"{c}{r}" for c in "gh" for r in (5, 6)
)

# Own territory: the four rows a side deploys into.
TERRITORY = {"R": (1, 2, 3, 4), "B": (7, 8, 9, 10)}
OPPONENT = {"R": "B", "B": "R"}

VARIANTS = {
    "classic": {
        "Marshal": 1, "General": 1, "Colonel": 2, "Major": 3, "Captain": 4,
        "Lieutenant": 4, "Sergeant": 4, "Miner": 5, "Scout": 8, "Spy": 1,
        "Bomb": 6, "Flag": 1,
    },  # 40 pieces
    "barrage": {
        "Marshal": 1, "General": 1, "Miner": 1, "Scout": 1, "Sergeant": 1,
        "Spy": 1, "Bomb": 1, "Flag": 1,
    },  # 8 pieces
}


# Material values used when a capped Game is adjudicated. Rank is the base,
# with three deliberate departures: Miner (only answer to a Bomb), Scout
# (mobility and information), Spy (kills the Marshal). Flag scores 0 because
# losing it ends the Game before adjudication can happen.
VALUE = {
    "Marshal": 10, "General": 9, "Colonel": 8, "Major": 7, "Captain": 6,
    "Spy": 6, "Lieutenant": 5, "Miner": 5, "Sergeant": 4, "Bomb": 4,
    "Scout": 3, "Flag": 0,
}


def roster_text(variant: str) -> str:
    """'1 Marshal (M), 1 General (9), ...' in rank order, for prompts."""
    counts = VARIANTS[variant]
    order = ["Marshal", "General", "Colonel", "Major", "Captain", "Lieutenant",
             "Sergeant", "Miner", "Scout", "Spy", "Bomb", "Flag"]
    return ", ".join(f"{counts[r]} {r} ({GLYPH[r]})" for r in order if r in counts)


def piece_count(variant: str) -> int:
    return sum(VARIANTS[variant].values())


def square(col_idx: int, row: int) -> str:
    return f"{COLS[col_idx]}{row}"


def parse_square(sq: str) -> tuple[int, int]:
    """'d7' -> (3, 7). Raises ValueError on anything malformed."""
    s = sq.strip().lower()
    if len(s) < 2 or s[0] not in COLS or not s[1:].isdigit():
        raise ValueError(f"not a square: {sq!r}")
    row = int(s[1:])
    if row not in ROWS:
        raise ValueError(f"row out of range: {sq!r}")
    return COLS.index(s[0]), row


def on_board(col_idx: int, row: int) -> bool:
    return 0 <= col_idx < 10 and 1 <= row <= 10


def is_lake(sq: str) -> bool:
    return sq in LAKES


def resolve_combat(attacker: str, defender: str) -> str:
    """Who dies. Returns 'defender', 'attacker', or 'both'.

    Capturing the Flag is a win and is handled by the caller; here it simply
    means the defender is removed.
    """
    if defender == "Flag":
        return "defender"
    if defender == "Bomb":
        return "defender" if attacker == "Miner" else "attacker"
    if attacker == "Spy" and defender == "Marshal":
        return "defender"
    a, d = RANK[attacker], RANK[defender]
    if a > d:
        return "defender"
    if a < d:
        return "attacker"
    return "both"
