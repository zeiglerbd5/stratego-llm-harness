"""An Agent: a Model plus its prompt, settings, and identity.

Two Agents may share a Model and differ only in Thinking Policy; they are still
two Agents, and may play each other.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

from . import rules as R
from .adapter import Completion, ModelProfile, complete
from .game import GameState, IllegalMove, Move, validate_deployment
from .observation import empty_board, render

_HERE = Path(__file__).parent
RULEBOOK = (_HERE / "rulebook.md").read_text(encoding="utf-8")
STRATEGY_GUIDE = (_HERE / "strategy_guide.md").read_text(encoding="utf-8")


def prompt_version(strategy_guide: bool = False) -> str:
    """Hash of everything that shapes what a Model is told. Two Games are only
    comparable if this matches."""
    h = hashlib.sha256()
    for name in ("agent.py", "observation.py", "rulebook.md"):
        h.update((_HERE / name).read_bytes())
    if strategy_guide:
        h.update((_HERE / "strategy_guide.md").read_bytes())
    return h.hexdigest()[:12]

# Rationale is ordered FIRST so generation reasons before it commits.
MOVE_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "from": {"type": "string"},
        "to": {"type": "string"},
        "scratchpad": {"type": "string"},
    },
    "required": ["rationale", "from", "to", "scratchpad"],
    "additionalProperties": False,
}

DEPLOY_SCHEMA = {
    "type": "object",
    "properties": {
        "rationale": {"type": "string"},
        "rows": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["rationale", "rows"],
    "additionalProperties": False,
}

GLYPH_TO_RANK = {v: k for k, v in R.GLYPH.items()}


@dataclass
class Turn:
    """Everything one turn produced, win or lose. Token counts sum every
    attempt, because a rejected attempt's thinking was still spent."""
    move: Move | None
    rationale: str
    scratchpad: str
    attempts: list[dict]
    reasoning: str = ""
    thinking_tokens: int = 0            # native reasoning trace (ADR-0001's axis)
    thinking_tokens_source: str = "none"
    completion_tokens: int = 0          # the provider's own count, as reported
    seconds: float = 0.0
    failure: str | None = None      # illegal_move | parse_failure | budget_exhausted


# Least trustworthy source wins, so one estimated attempt marks the whole turn.
_SOURCE_RANK = {"estimate": 3, "tokenizer": 2, "provider": 1, "none": 0}


def _merge_sources(sources: set[str]) -> str:
    return max(sources, key=lambda s: _SOURCE_RANK.get(s, 0)) if sources else "none"


def _attempt(i: int, comp: Completion) -> dict:
    return {"attempt": i, "seconds": comp.seconds,
            "prompt_tokens": comp.prompt_tokens,
            "completion_tokens": comp.completion_tokens,
            "thinking_tokens": comp.thinking_tokens,
            "thinking_tokens_source": comp.thinking_tokens_source,
            "finish_reason": comp.finish_reason,
            "reasoning_chars": len(comp.reasoning)}


class Agent:
    def __init__(self, name: str, profile: ModelProfile, color: str,
                 thinking: str = "standard", move_assist: str = "full",
                 threat_assist: str = "full", strategy_guide: bool = False,
                 retries: int = 3):
        self.name = name
        self.profile = profile
        self.color = color
        self.thinking = thinking
        self.move_assist = move_assist
        self.threat_assist = threat_assist
        self.strategy_guide = strategy_guide
        self.retries = retries
        self.scratchpad = ""
        self.variant = "classic"

    # ---------- shared ----------

    def _system(self) -> str:
        # Bare objective only. Any tactical steer belongs in the Strategy Guide,
        # which is off by default so the benchmark measures the Model.
        n = R.piece_count(self.variant)
        text = (
            "You are playing Stratego. You win by capturing the enemy Flag and "
            "lose if yours is captured. Play to win.\n\n"
            f"This Game is the {self.variant.capitalize()} variant. Each side has "
            f"exactly {n} pieces: {R.roster_text(self.variant)}.\n\n"
            + RULEBOOK
        )
        if self.strategy_guide:
            text += "\n\n" + STRATEGY_GUIDE
        return text

    def _ask(self, user: str, schema: dict, budget: int | None = None) -> Completion:
        return complete(
            self.profile,
            [{"role": "system", "content": self._system()},
             {"role": "user", "content": user}],
            schema, thinking=self.thinking, max_tokens=budget)

    @staticmethod
    def _parse(comp: Completion) -> dict:
        text = comp.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1].lstrip("json").strip()
        return json.loads(text)

    # ---------- deployment ----------

    def deploy(self, variant: str) -> tuple[dict[str, str], str, list[dict]]:
        self.variant = variant
        counts = R.VARIANTS[variant]
        rows = list(R.TERRITORY[self.color])
        if self.color == "B":
            rows = rows[::-1]           # back row first for both colours
        roster = ", ".join(f"{n}x {rank} ('{R.GLYPH[rank]}')"
                           for rank, n in counts.items())
        you = "RED" if self.color == "R" else "BLUE"
        enemy_rows = R.TERRITORY[R.OPPONENT[self.color]]
        prompt = (
            f"Write your opening Deployment as {you}.\n\n"
            f"The board ('~' = lake, impassable). You deploy in rows "
            f"{min(rows)}-{max(rows)}; the enemy deploys in rows "
            f"{enemy_rows[0]}-{enemy_rows[-1]} at the same time and cannot see "
            f"your placement.\n\n{empty_board()}\n\n"
            f"Your pieces: {roster}.\n"
            f"Give exactly 4 rows of 10 space-separated cells, using the glyph for a "
            f"piece or '.' for empty. rows[0] is your BACK row (row {rows[0]}, "
            f"furthest from the enemy) and rows[3] is your FRONT row (row {rows[3]}, "
            f"facing the enemy).\n"
            f"Every piece listed must appear exactly the stated number of times.\n"
            f"Example row format: \"F B . . . . . . . .\""
        )
        attempts: list[dict] = []
        err = ""
        for i in range(self.retries):
            comp = self._ask(prompt + err, DEPLOY_SCHEMA)
            rec = _attempt(i, comp)
            try:
                data = self._parse(comp)
                dep = self._rows_to_deployment(data["rows"], rows)
                validate_deployment(dep, self.color, variant)
                rec["ok"] = True
                attempts.append(rec)
                return dep, data.get("rationale", ""), attempts
            except (json.JSONDecodeError, KeyError, ValueError, IllegalMove) as e:
                rec["ok"] = False
                rec["error"] = str(e)[:300]
                # IllegalMove and JSONDecodeError are both ValueErrors: ask, don't order.
                rec["error_kind"] = getattr(e, "kind", None) or (
                    "parse" if isinstance(e, json.JSONDecodeError) else "format")
                attempts.append(rec)
                err = (f"\n\nYour previous attempt was rejected: {e}\n"
                      f"Reply with exactly 4 rows of 10 cells each. Correct it.")
        return {}, "", attempts

    @staticmethod
    def _rows_to_deployment(rows: list[str], row_numbers: list[int]) -> dict[str, str]:
        if len(rows) != 4:
            raise ValueError(f"expected 4 rows, got {len(rows)}")
        dep: dict[str, str] = {}
        for row_str, row_no in zip(rows, row_numbers):
            cells = row_str.split()
            if len(cells) != 10:
                # Glyphs are single characters, so an unspaced row is unambiguous.
                compact = "".join(row_str.split())
                if len(compact) == 10:
                    cells = list(compact)
                else:
                    raise ValueError(
                        f"row {row_no} has {len(cells)} cells, expected 10 "
                        f"(use 10 space-separated glyphs, '.' for empty)")
            for c, cell in enumerate(cells):
                if cell == ".":
                    continue
                if cell not in GLYPH_TO_RANK:
                    raise ValueError(f"{cell!r} is not a piece glyph")
                dep[R.square(c, row_no)] = GLYPH_TO_RANK[cell]
        return dep

    # ---------- moving ----------

    def choose_move(self, st: GameState) -> Turn:
        self.variant = st.variant
        obs = render(st, self.color, self.scratchpad, self.move_assist,
                     self.threat_assist)
        prompt = (
            obs
            + "\n\nChoose one Move. Answer as JSON with these fields in order:\n"
              "  rationale  - one or two sentences on why this Move\n"
              "  from, to   - squares, e.g. \"d7\"\n"
              "  scratchpad - notes to your future self; you will see these next "
              "turn and nothing else carries over.\n"
              "Your rationale and scratchpad are private. The enemy never sees them."
        )
        attempts: list[dict] = []
        feedback = ""
        budget = None
        total_think = 0
        total_completion = 0
        sources: set[str] = set()
        total_secs = 0.0
        last_reasoning = ""
        failure = None

        for i in range(self.retries):
            comp = self._ask(prompt + feedback, MOVE_SCHEMA, budget)
            total_secs += comp.seconds
            total_think += comp.thinking_tokens
            total_completion += comp.completion_tokens
            sources.add(comp.thinking_tokens_source)
            last_reasoning = comp.reasoning or last_reasoning
            rec = _attempt(i, comp)

            if comp.budget_exhausted:
                # Spent its thinking budget and returned nothing. This is not an
                # illegal Move and is retried once at a raised budget. If the
                # context window bound first, that is the harness's ceiling,
                # not the Model's, and is labelled so (ADR-0001 counts hits).
                rec["ok"] = False
                rec["failure"] = "budget_exhausted"
                rec["ceiling"] = "context" if comp.context_bound else "budget"
                attempts.append(rec)
                failure = "budget_exhausted"
                budget = int((budget or self.profile.max_tokens) * 2)
                feedback = "\n\nYou ran out of output budget. Think briefly, then answer."
                continue

            try:
                data = self._parse(comp)
                mv = Move(str(data["from"]).strip().lower(),
                          str(data["to"]).strip().lower())
            except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
                rec["ok"] = False
                rec["failure"] = "parse_failure"
                rec["error"] = str(e)[:200]
                attempts.append(rec)
                failure = "parse_failure"
                feedback = f"\n\nYour previous reply could not be parsed: {e} Reply with JSON only."
                continue

            try:
                st.validate(mv, self.color)
            except IllegalMove as e:
                rec["ok"] = False
                rec["failure"] = "illegal_move"
                rec["error_kind"] = e.kind
                rec["error"] = str(e)
                rec["move"] = str(mv)
                attempts.append(rec)
                failure = "illegal_move"
                feedback = f"\n\nYour Move {mv} was rejected: {e} Choose a different Move."
                continue

            rec["ok"] = True
            rec["move"] = str(mv)
            attempts.append(rec)
            self.scratchpad = str(data.get("scratchpad", ""))[:1200]
            return Turn(mv, str(data.get("rationale", "")), self.scratchpad,
                        attempts, last_reasoning, total_think,
                        _merge_sources(sources), total_completion,
                        round(total_secs, 2))

        return Turn(None, "", self.scratchpad, attempts, last_reasoning,
                    total_think, _merge_sources(sources), total_completion,
                    round(total_secs, 2), failure=failure)
