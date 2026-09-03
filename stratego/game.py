"""Game state, Move Validation, and terminal conditions.

The engine is authoritative: an Agent never mutates state, it proposes a Move
which is validated before it is applied.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field

from . import rules as R


@dataclass
class Piece:
    id: int
    color: str
    rank: str
    square: str | None
    revealed: bool = False          # rank seen by the opponent in Combat
    move_count: int = 0
    moved_far: bool = False         # opponent has seen it move >1 square
    own_moves: list[tuple[str, str]] = field(default_factory=list)

    @property
    def alive(self) -> bool:
        return self.square is not None

    @property
    def mobile(self) -> bool:
        return self.rank not in R.IMMOBILE


class IllegalMove(ValueError):
    """Raised with a rule-citing message an Agent can act on, and a `kind`
    the harness can count: bad_square | no_piece | not_yours | immobile |
    no_move | lake | own_piece | repetition | scout_blocked | not_adjacent |
    deployment."""

    def __init__(self, message: str, kind: str = "other"):
        super().__init__(message)
        self.kind = kind


@dataclass
class Move:
    frm: str
    to: str

    def __str__(self) -> str:
        return f"{self.frm}-{self.to}"


@dataclass
class GameState:
    variant: str = "barrage"
    move_cap: int = 400
    pieces: dict[int, Piece] = field(default_factory=dict)
    to_move: str = "R"
    ply: int = 0
    log: list[dict] = field(default_factory=list)
    result: str | None = None       # 'R', 'B', or 'draw'
    result_reason: str | None = None

    REPETITION_WINDOW = 5      # a piece's own recent Moves considered
    REPETITION_REVISITS = 3    # ...returning to one square this often is a shuffle

    # ---------- construction ----------

    @classmethod
    def from_deployments(cls, red: dict[str, str], blue: dict[str, str],
                         variant: str = "barrage", move_cap: int = 400) -> "GameState":
        """red/blue map square -> rank. Both are validated before the Game starts."""
        st = cls(variant=variant, move_cap=move_cap)
        pid = 0
        for color, dep in (("R", red), ("B", blue)):
            validate_deployment(dep, color, variant)
            for sq, rank in dep.items():
                st.pieces[pid] = Piece(id=pid, color=color, rank=rank, square=sq)
                pid += 1
        return st

    # ---------- queries ----------

    def at(self, sq: str) -> Piece | None:
        for p in self.pieces.values():
            if p.square == sq:
                return p
        return None

    def occupied(self) -> dict[str, Piece]:
        return {p.square: p for p in self.pieces.values() if p.alive}

    def side(self, color: str) -> list[Piece]:
        return [p for p in self.pieces.values() if p.color == color and p.alive]

    def captured(self, color: str) -> list[str]:
        """Ranks of `color` pieces that have been removed. Public information."""
        return sorted(p.rank for p in self.pieces.values()
                      if p.color == color and not p.alive)

    def legal_moves(self, color: str | None = None) -> list[Move]:
        color = color or self.to_move
        occ = self.occupied()
        out: list[Move] = []
        for p in self.side(color):
            if not p.mobile:
                continue
            c, r = R.parse_square(p.square)
            reach = 9 if p.rank == "Scout" else 1
            for dc, dr in ((0, 1), (0, -1), (1, 0), (-1, 0)):
                for step in range(1, reach + 1):
                    nc, nr = c + dc * step, r + dr * step
                    if not R.on_board(nc, nr):
                        break
                    t = R.square(nc, nr)
                    if R.is_lake(t):
                        break
                    other = occ.get(t)
                    if other and other.color == color:
                        break
                    mv = Move(p.square, t)
                    if not self._repetition_violation(p, mv):
                        out.append(mv)
                    if other:
                        break          # may attack, may not pass through
        return out

    def _repetition_violation(self, p: Piece, mv: Move) -> bool:
        """Rulebook Sec.5. Covers both the two-square and more-square rules.

        Two-square: the same shuttle Move may not be made a third time.
        More-square: a piece may not return to the same square three times
        across a run of its own recent Moves. Without the second clause a piece
        simply rotates its partner square and shuttles forever - which is
        exactly what a weak model does when it has nothing better to play.
        """
        pair = {mv.frm, mv.to}
        seen = 0
        for frm, to in reversed(p.own_moves):
            if {frm, to} != pair:
                break
            if (frm, to) == (mv.frm, mv.to):
                seen += 1
        if seen >= 2:
            return True

        window = p.own_moves[-self.REPETITION_WINDOW:]
        if len(window) < self.REPETITION_WINDOW:
            return False
        destinations = [to for _, to in window] + [mv.to]
        return max(destinations.count(d) for d in set(destinations)) >= self.REPETITION_REVISITS

    # ---------- validation ----------

    def validate(self, mv: Move, color: str) -> None:
        """Raise IllegalMove with a Rulebook-citing message, or return silently."""
        try:
            R.parse_square(mv.frm), R.parse_square(mv.to)
        except ValueError as e:
            raise IllegalMove(f"{e}. Squares are a-j paired with 1-10, e.g. 'd7'.",
                              "bad_square")
        p = self.at(mv.frm)
        if p is None:
            raise IllegalMove(f"No piece on {mv.frm}.", "no_piece")
        if p.color != color:
            raise IllegalMove(f"The piece on {mv.frm} is not yours.", "not_yours")
        if not p.mobile:
            raise IllegalMove(
                f"{p.rank} on {mv.frm} can never move. See Rulebook Sec.3 Movement.",
                "immobile")
        if mv.frm == mv.to:
            raise IllegalMove("A Move must change square. Passing is not allowed.",
                              "no_move")
        if R.is_lake(mv.to):
            raise IllegalMove(
                f"{mv.to} is a lake and cannot be entered. See Rulebook Sec.2 Board.",
                "lake")
        target = self.at(mv.to)
        if target and target.color == color:
            raise IllegalMove(f"{mv.to} holds your own {target.rank}.", "own_piece")
        if mv not in self.legal_moves(color):
            if self._repetition_violation(p, mv):
                raise IllegalMove(
                    f"{mv} shuffles this piece among squares it keeps returning to. "
                    "See Rulebook Sec.5 Repetition.", "repetition")
            if p.rank == "Scout":
                raise IllegalMove(
                    f"{mv} is blocked: a Scout slides in a straight line through "
                    "empty squares only. See Rulebook Sec.3 Movement.", "scout_blocked")
            raise IllegalMove(
                f"{mv} is not a straight one-square step. Only Scouts move "
                "further than one square. See Rulebook Sec.3 Movement.", "not_adjacent")

    # ---------- mutation ----------

    def apply(self, mv: Move) -> dict:
        """Apply a validated Move. Returns the event that was recorded."""
        color = self.to_move
        self.validate(mv, color)
        p = self.at(mv.frm)
        target = self.at(mv.to)
        dist = abs(R.parse_square(mv.frm)[0] - R.parse_square(mv.to)[0]) + \
               abs(R.parse_square(mv.frm)[1] - R.parse_square(mv.to)[1])

        event = {"ply": self.ply, "color": color, "move": str(mv),
                 "rank": p.rank, "combat": None}

        if target is None:
            p.square = mv.to
        else:
            outcome = R.resolve_combat(p.rank, target.rank)
            event["combat"] = {"attacker": p.rank, "defender": target.rank,
                               "outcome": outcome, "square": mv.to}
            # Combat reveals both pieces to both players.
            p.revealed = target.revealed = True
            if outcome == "defender":
                target.square = None
                p.square = mv.to
            elif outcome == "attacker":
                p.square = None
            else:
                p.square = None
                target.square = None
            if target.rank == "Flag":
                self.result, self.result_reason = color, "flag_captured"

        p.move_count += 1
        p.own_moves.append((mv.frm, mv.to))
        if dist > 1:
            p.moved_far = True          # only a Scout can do this
        self.ply += 1
        self.to_move = R.OPPONENT[color]
        self.log.append(event)
        self._check_terminal()
        return event

    def _check_terminal(self) -> None:
        if self.result:
            return
        if self.ply >= self.move_cap:
            self.result, self.result_reason = "draw", "move_cap"
            return
        if not self.legal_moves(self.to_move):
            self.result = R.OPPONENT[self.to_move]
            self.result_reason = "no_legal_moves"

    def concede(self, color: str, reason: str) -> None:
        self.result, self.result_reason = R.OPPONENT[color], reason


# ---------- deployment ----------

def validate_deployment(dep: dict[str, str], color: str, variant: str) -> None:
    want = R.VARIANTS[variant]
    rows = R.TERRITORY[color]
    got: dict[str, int] = {}
    for sq, rank in dep.items():
        if rank not in want:
            raise IllegalMove(f"{rank!r} is not a piece in the {variant} variant.",
                              "deployment")
        _, row = R.parse_square(sq)
        if row not in rows:
            raise IllegalMove(
                f"{sq} is outside your territory (rows {rows[0]}-{rows[-1]}).",
                "deployment")
        got[rank] = got.get(rank, 0) + 1

    # Name every wrong rank. "9 pieces, expected 8" tells a model nothing it can
    # act on; "you placed 2x Scout, need 1x" tells it exactly what to change.
    problems = []
    for rank, n in want.items():
        have = got.get(rank, 0)
        if have > n:
            problems.append(f"{have}x {rank} ('{R.GLYPH[rank]}') but need exactly {n}")
        elif have < n:
            problems.append(f"only {have}x {rank} ('{R.GLYPH[rank]}') but need {n}")
    if problems:
        raise IllegalMove(
            f"You placed {len(dep)} pieces, need {sum(want.values())}. Wrong: "
            + "; ".join(problems) + ".", "deployment")


def random_deployment(color: str, variant: str, rng: random.Random) -> dict[str, str]:
    """A legal but unskilled Deployment. Used for the library and for tests."""
    ranks = [r for r, n in R.VARIANTS[variant].items() for _ in range(n)]
    squares = [R.square(c, r) for r in R.TERRITORY[color] for c in range(10)]
    rng.shuffle(squares)
    rng.shuffle(ranks)
    return dict(zip(squares[:len(ranks)], ranks))
