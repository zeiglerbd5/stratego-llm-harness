"""Renders what an Agent is permitted to know, as the text it actually receives.

Principle: bookkeeping is the harness's job, judgment is the Agent's. Anything a
human would track on a scratch pad - remaining enemy pieces, material, what can
attack what - is supplied. What to do about it is not.

Coordinates are absolute for both sides (never mirrored): a model that has to
transform coordinates spends its budget on arithmetic instead of strategy.
"""
from __future__ import annotations

from . import rules as R
from .game import GameState

MOVE_LOG_TAIL = 12


def _grid(st: GameState, me: str) -> str:
    occ = st.occupied()
    lines = ["    " + " ".join(R.COLS)]
    for row in range(10, 0, -1):
        cells = []
        for c in range(10):
            sq = R.square(c, row)
            p = occ.get(sq)
            if R.is_lake(sq):
                cells.append("~")
            elif p is None:
                cells.append(".")
            elif p.color == me:
                cells.append(R.GLYPH[p.rank])
            elif p.revealed:
                cells.append("!")
            else:
                cells.append("?")
        lines.append(f"{row:>3} " + " ".join(cells) + f" {row}")
    lines.append("    " + " ".join(R.COLS))
    return "\n".join(lines)


def empty_board() -> str:
    """The bare board for the Deployment prompt: lakes define the lanes."""
    lines = ["    " + " ".join(R.COLS)]
    for row in range(10, 0, -1):
        cells = ["~" if R.is_lake(R.square(c, row)) else "." for c in range(10)]
        lines.append(f"{row:>3} " + " ".join(cells) + f" {row}")
    lines.append("    " + " ".join(R.COLS))
    return "\n".join(lines)


def _enemy_notes(st: GameState, me: str) -> list[str]:
    notes = []
    for p in sorted(st.side(R.OPPONENT[me]), key=lambda x: x.square):
        bits = []
        if p.revealed:
            bits.append(f"known {p.rank}")
        elif p.moved_far:
            bits.append("moved >1 square, so it is a Scout")
        if p.move_count == 0:
            bits.append("never moved")
        elif not p.revealed:
            bits.append(f"{p.move_count} move" + ("s" if p.move_count != 1 else "") + " made")
        notes.append(f"  {p.square}: {'; '.join(bits)}")
    return notes


def _remaining(st: GameState, color: str) -> str:
    """Pieces `color` still has, by rank, with counts. Public information."""
    counts = dict(R.VARIANTS[st.variant])
    for rank in st.captured(color):
        counts[rank] -= 1
    order = ["Marshal", "General", "Colonel", "Major", "Captain", "Lieutenant",
             "Sergeant", "Miner", "Scout", "Spy", "Bomb", "Flag"]
    parts = []
    for r in order:
        n = counts.get(r, 0)
        if n == 1:
            parts.append(r)
        elif n > 1:
            parts.append(f"{n}x {r}")
    return ", ".join(parts) or "nothing"


def _material(st: GameState) -> dict[str, int]:
    return {c: sum(R.VALUE[p.rank] for p in st.side(c)) for c in ("R", "B")}


def _legal_by_piece(st: GameState, me: str) -> tuple[str, int]:
    moves = st.legal_moves(me)
    grouped: dict[str, list[str]] = {}
    for m in moves:
        grouped.setdefault(m.frm, []).append(m.to)
    occ = st.occupied()
    lines = [f"  {frm} {occ[frm].rank}: {' '.join(grouped[frm])}" for frm in sorted(grouped)]
    return "\n".join(lines), len(moves)


def _threats(st: GameState, me: str, level: str) -> list[str]:
    """What the enemy can attack on its next move. The defensive mirror of the
    Legal Move List: the same facts, from the other side of the board."""
    if level == "none":
        return []
    occ = st.occupied()
    by_target: dict[str, list[str]] = {}
    for m in st.legal_moves(R.OPPONENT[me]):
        tgt = occ.get(m.to)
        if tgt and tgt.color == me:
            att = occ[m.frm]
            tag = att.rank if att.revealed else ("Scout" if att.moved_far else "?")
            by_target.setdefault(m.to, []).append(f"{m.frm}({tag})")
    if not by_target:
        return ["THREATS: none of your pieces can be attacked next move."]
    if level == "hints":
        return ["THREATENED NEXT MOVE: " + " ".join(sorted(by_target))]
    lines = ["THREATS - your pieces the enemy can attack next move:"]
    for sq in sorted(by_target):
        lines.append(f"  {sq} {occ[sq].rank} <- {', '.join(by_target[sq])}")
    return lines


def render(st: GameState, me: str, scratchpad: str = "",
           move_assist: str = "full", threat_assist: str = "full") -> str:
    """The Observation. Both assists are none | hints | full."""
    you = "RED" if me == "R" else "BLUE"
    them = R.OPPONENT[me]
    home = R.TERRITORY[me]
    mine = sorted(st.side(me), key=lambda p: p.square)
    mat = _material(st)
    remaining = st.move_cap - st.ply

    parts = [
        f"MOVE {st.ply + 1} of {st.move_cap} - {remaining} remain. "
        f"If the cap is reached the Game is decided on surviving material.",
        "",
        f"You are {you}. Your home rows are {home[0]}-{home[-1]}; "
        f"the enemy deploys in rows {R.TERRITORY[them][0]}-{R.TERRITORY[them][-1]}.",
        "",
        "BOARD  ('~' lake, '.' empty, '?' unknown enemy, '!' enemy of known rank - see ENEMY PIECES)",
        _grid(st, me),
        # Named as well as drawn: a Model that misreads the grid has read a
        # lake as empty and concluded the Legal Move List was wrong.
        "LAKES (impassable, always empty): " + " ".join(sorted(R.LAKES, key=R.parse_square)),
        "",
        "YOUR PIECES: " + ", ".join(f"{p.square}={p.rank}" for p in mine),
    ]
    if move_assist == "hints":
        movable = sorted({m.frm for m in st.legal_moves(me)})
        parts.append("YOUR PIECES THAT CAN MOVE: " + (" ".join(movable) or "none"))

    enemy = _enemy_notes(st, me)
    parts += ["", f"ENEMY PIECES ({len(enemy)} on board):"] + (enemy or ["  none"])
    parts += [f"ENEMY STILL HAS: {_remaining(st, them)}"]

    parts += [
        "",
        f"YOUR LOSSES: {', '.join(st.captured(me)) or 'none'}",
        f"ENEMY LOSSES: {', '.join(st.captured(them)) or 'none'}",
        f"MATERIAL (adjudication points): you {mat[me]}, enemy {mat[them]}",
    ]

    if st.log:
        tail = st.log[-MOVE_LOG_TAIL:]
        entries = []
        for e in tail:
            s = f"{e['color']}:{e['move']}"
            if e["combat"]:
                c = e["combat"]
                s += f"({c['attacker']}x{c['defender']}->{c['outcome']})"
            entries.append(s)
        parts += ["", f"MOVE LOG (last {len(tail)} of {len(st.log)}): " + " ".join(entries)]

    if scratchpad:
        parts += ["", "YOUR NOTES FROM LAST TURN:", scratchpad]

    if move_assist == "full":
        body, n = _legal_by_piece(st, me)
        parts += ["", f"LEGAL MOVES ({n}) - this list is complete. A square not shown "
                      "is unreachable this turn (lake, blocked, or Sec.5 Repetition). "
                      "Choose one of these:", body]

    # After the Legal Move List, not before it. Listed ahead of everything a
    # Model could do, the threats framed every turn as defence, and a Model
    # that follows instructions spent whole Games retreating.
    threats = _threats(st, me, threat_assist)
    if threats:
        parts += [""] + threats

    return "\n".join(parts)
