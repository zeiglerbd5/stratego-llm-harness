"""Plays one Game between two Agents and writes the Game Record."""
from __future__ import annotations

import random
from pathlib import Path

from . import rules as R
from .adapter import ensure_context
from .agent import Agent, prompt_version
from . import deployments as lib
from .game import GameState, random_deployment
from .metrics import adjudicate, material
from .record import GameRecord

FORFEIT_LIMIT = 5


def play_game(red: Agent, blue: Agent, variant: str = "barrage",
              move_cap: int = 400, out: str | Path = "records/game.jsonl",
              seed: int = 0, verbose: bool = True,
              deployment: str = "model",
              openings: dict[str, str | None] | None = None) -> dict:
    """`deployment` is model | library | random.

    `openings` names the library entry per colour, e.g.
    {"R": "corner-fortress", "B": "far-corner"}. The two are never the same:
    see `deployments.pair`. A paired Game swaps the Models between the seats
    and keeps the openings with the seats, so the position is identical.
    """
    rng = random.Random(seed)
    for ag in (red, blue):
        ensure_context(ag.profile)      # before game_start, so it is recorded
    chosen = lib.pair(variant, openings or {}, rng) if deployment == "library" else None
    rec = GameRecord(out, {
        "variant": variant, "move_cap": move_cap, "seed": seed,
        "deployment_source": deployment, "openings": chosen,
        "prompt_version": prompt_version(red.strategy_guide or blue.strategy_guide),
        "red": {"agent": red.name, "model": red.profile.name,
                "served_as": red.profile.served_name,
                "context_tokens": red.profile.context_tokens,
                "max_tokens": red.profile.max_tokens,
                "thinking": red.thinking, "move_assist": red.move_assist,
                "threat_assist": red.threat_assist,
                "strategy_guide": red.strategy_guide},
        "blue": {"agent": blue.name, "model": blue.profile.name,
                 "served_as": blue.profile.served_name,
                 "context_tokens": blue.profile.context_tokens,
                 "max_tokens": blue.profile.max_tokens,
                 "thinking": blue.thinking, "move_assist": blue.move_assist,
                 "threat_assist": blue.threat_assist,
                 "strategy_guide": blue.strategy_guide},
    })

    deployments: dict[str, dict[str, str]] = {}
    contaminated = []
    for ag in (red, blue):
        if deployment == "library":
            dep, entry = lib.get(variant, ag.color, chosen[ag.color], rng)
            why, attempts = f"library Deployment {entry!r}", []
        elif deployment == "random":
            dep, why, attempts = random_deployment(ag.color, variant, rng), "random", []
        else:
            dep, why, attempts = ag.deploy(variant)
        if not dep:
            dep = random_deployment(ag.color, variant, rng)
            contaminated.append(ag.color)
            why = "(deployment failed validation; random Deployment substituted)"
        deployments[ag.color] = dep
        rec.write("deployment", color=ag.color, agent=ag.name, deployment=dep,
                  rationale=why, attempts=attempts,
                  substituted=ag.color in contaminated)
        if verbose:
            print(f"  {ag.name} ({ag.color}) deployed"
                  + (" [SUBSTITUTED]" if ag.color in contaminated else ""))

    st = GameState.from_deployments(deployments["R"], deployments["B"],
                                    variant=variant, move_cap=move_cap)
    agents = {"R": red, "B": blue}
    forfeits = {"R": 0, "B": 0}
    tally = {"illegal_move": 0, "parse_failure": 0, "budget_exhausted": 0}

    while st.result is None:
        ag = agents[st.to_move]
        turn = ag.choose_move(st)
        for a in turn.attempts:
            if a.get("failure"):
                tally[a["failure"]] = tally.get(a["failure"], 0) + 1

        if turn.move is None:
            forfeits[ag.color] += 1
            legal = st.legal_moves(ag.color)
            substitute = legal[rng.randrange(len(legal))]
            rec.write("forfeit", ply=st.ply, color=ag.color, agent=ag.name,
                      failure=turn.failure, substituted=str(substitute),
                      attempts=turn.attempts, seconds=turn.seconds,
                      thinking_tokens=turn.thinking_tokens,
                      thinking_tokens_source=turn.thinking_tokens_source,
                      completion_tokens=turn.completion_tokens,
                      forfeits_so_far=forfeits[ag.color])
            if verbose:
                print(f"  ply {st.ply:>3} {ag.color} FORFEIT ({turn.failure}) "
                      f"-> {substitute}")
            if forfeits[ag.color] >= FORFEIT_LIMIT:
                st.concede(ag.color, "forfeit_limit")
                break
            event = st.apply(substitute)
        else:
            event = st.apply(turn.move)
            # Every attempt is written, not just the count: a rejected Move's
            # error kind is the evidence for whether a Model misread the board
            # or broke a rule, and it is gone if only the retry count survives.
            rec.write("move", ply=event["ply"], color=ag.color, agent=ag.name,
                      move=event["move"], rank=event["rank"],
                      combat=event["combat"], rationale=turn.rationale,
                      scratchpad=turn.scratchpad, reasoning=turn.reasoning,
                      thinking_tokens=turn.thinking_tokens,
                      thinking_tokens_source=turn.thinking_tokens_source,
                      completion_tokens=turn.completion_tokens,
                      seconds=turn.seconds, retries=len(turn.attempts) - 1,
                      attempts=turn.attempts)
            if verbose:
                c = event["combat"]
                extra = (f"  [{c['attacker']} x {c['defender']} -> {c['outcome']}]"
                         if c else "")
                print(f"  ply {event['ply']:>3} {ag.color} {event['move']:<8}"
                      f" {event['rank']:<10}{extra}  ({turn.seconds}s)"
                      f"  {turn.rationale[:60]}")

    mat = material(st)
    adj_result, adj_reason = (
        adjudicate(st) if (st.result == "draw" and st.result_reason == "move_cap")
        else (st.result, st.result_reason))
    summary = {
        "result": st.result, "reason": st.result_reason, "plies": st.ply,
        "material": mat,
        "adjudicated_result": adj_result, "adjudicated_reason": adj_reason,
        "forfeits": forfeits, "failures": tally,
        "deployment_substituted": contaminated,
    }
    rec.close(**summary)
    return summary
