"""The engine: rules, Move Validation, repetition, Deployments, the Observation.

Stdlib unittest, no network, runs in well under a second:

    python3 -m unittest discover -s tests -v
"""
from __future__ import annotations

import random
import unittest

from stratego import deployments as lib
from stratego import rules as R
from stratego.game import GameState, IllegalMove, Move, random_deployment, validate_deployment
from stratego.observation import render


def position(red="far-corner", blue="centre-guard", variant="barrage") -> GameState:
    """Red far-corner: Scout d4, Marshal f4, Miner h3, General h4, Sergeant i1,
    Spy i2, Flag j1, Bomb j2. Blue centre-guard: Scout b7, General d7, Marshal g7."""
    r, _ = lib.get(variant, "R", red)
    b, _ = lib.get(variant, "B", blue)
    return GameState.from_deployments(r, b, variant=variant, move_cap=60)


class Combat(unittest.TestCase):
    def test_rank_order(self):
        self.assertEqual(R.resolve_combat("Marshal", "General"), "defender")
        self.assertEqual(R.resolve_combat("Scout", "Sergeant"), "attacker")
        self.assertEqual(R.resolve_combat("General", "General"), "both")

    def test_spy_only_wins_when_attacking_the_marshal(self):
        self.assertEqual(R.resolve_combat("Spy", "Marshal"), "defender")
        self.assertEqual(R.resolve_combat("Marshal", "Spy"), "defender")
        self.assertEqual(R.resolve_combat("Spy", "Scout"), "attacker")

    def test_bombs_and_flags(self):
        self.assertEqual(R.resolve_combat("Marshal", "Bomb"), "attacker")
        self.assertEqual(R.resolve_combat("Miner", "Bomb"), "defender")
        self.assertEqual(R.resolve_combat("Scout", "Flag"), "defender")

    def test_variants(self):
        self.assertEqual(R.piece_count("barrage"), 8)
        self.assertEqual(R.piece_count("classic"), 40)


class Validation(unittest.TestCase):
    """Every rejection carries a kind the harness can count."""

    def rejects(self, st, frm, to, kind, color="R"):
        with self.assertRaises(IllegalMove) as cm:
            st.validate(Move(frm, to), color)
        self.assertEqual(cm.exception.kind, kind, str(cm.exception))

    def test_kinds(self):
        st = position()   # Red: Scout d4, Marshal f4, Miner h3, General h4, Flag j1, Bomb j2
        self.rejects(st, "d4", "d5", "lake")
        self.rejects(st, "f4", "f6", "not_adjacent")
        self.rejects(st, "d4", "d7", "scout_blocked")
        self.rejects(st, "h3", "h4", "own_piece")
        self.rejects(st, "j1", "j2", "immobile")
        self.rejects(st, "a1", "a2", "no_piece")
        self.rejects(st, "g7", "g6", "not_yours")
        self.rejects(st, "z9", "a1", "bad_square")
        self.rejects(st, "f4", "f4", "no_move")

    def test_every_listed_move_is_legal_and_nothing_else_is(self):
        st = position()
        legal = st.legal_moves("R")
        self.assertGreater(len(legal), 0)
        for mv in legal:
            st.validate(mv, "R")
        self.rejects(st, "h4", "h5", "lake")

    def test_scout_slides_and_attacks_but_never_jumps(self):
        st = position()
        st.apply(Move("d4", "d1"))            # Red Scout down the file
        st.apply(Move("d7", "d8"))            # Blue Scout
        st.validate(Move("d1", "d4"), "R")    # three empty squares in a line
        self.rejects(st, "d1", "e2", "scout_blocked")   # a diagonal is not a line

    def test_repetition_rule(self):
        st = position()
        scout = st.at("d4")
        scout.own_moves = [("d4", "d3"), ("d3", "d4"), ("d4", "d3"), ("d3", "d4")]
        self.rejects(st, "d4", "d3", "repetition")
        scout.own_moves = []
        st.validate(Move("d4", "d3"), "R")


class Terminal(unittest.TestCase):
    def test_flag_capture_ends_the_game(self):
        red = {"a1": "Flag", "a2": "Bomb", "b1": "Spy", "c1": "Miner", "d1": "Sergeant",
               "e1": "General", "f1": "Marshal", "j4": "Scout"}
        blue = {"j10": "Flag", "i10": "Bomb", "a10": "Spy", "b10": "Scout", "c10": "Miner",
                "d10": "Sergeant", "e10": "General", "f10": "Marshal"}
        st = GameState.from_deployments(red, blue, variant="barrage", move_cap=400)
        st.apply(Move("j4", "j9"))            # the j-file has no lakes
        st.apply(Move("b10", "b9"))
        self.assertIsNone(st.result)
        st.apply(Move("j9", "j10"))
        self.assertEqual((st.result, st.result_reason), ("R", "flag_captured"))

    def test_no_legal_moves_loses(self):
        red = {"a1": "Flag", "a2": "Bomb", "b1": "Spy", "c1": "Miner", "d1": "Sergeant",
               "e1": "General", "f1": "Marshal", "j4": "Scout"}
        blue = {"j10": "Flag", "j9": "Bomb", "a10": "Spy", "b10": "Scout", "c10": "Miner",
                "d10": "Sergeant", "e10": "General", "f10": "Marshal"}
        st = GameState.from_deployments(red, blue, variant="barrage", move_cap=400)
        # Strip Blue to Flag and Bomb by hand, then let Red move: Blue is stuck.
        for p in list(st.pieces.values()):
            if p.color == "B" and p.rank not in ("Flag", "Bomb"):
                p.square = None
        st.apply(Move("j4", "j5"))
        self.assertEqual((st.result, st.result_reason), ("R", "no_legal_moves"))

    def test_move_cap_is_a_draw(self):
        st = position()
        st.move_cap = 2
        st.apply(Move("d4", "d3"))
        st.apply(Move("d7", "d8"))
        self.assertEqual((st.result, st.result_reason), ("draw", "move_cap"))


class Deployments(unittest.TestCase):
    def test_library_is_legal_for_both_colours(self):
        self.assertEqual(lib.validate_library(), [])

    def test_pair_never_mirrors(self):
        for seed in range(200):
            p = lib.pair("barrage", {}, random.Random(seed))
            self.assertNotEqual(p["R"], p["B"])

    def test_pair_refuses_a_mirror_and_unknown_names(self):
        with self.assertRaises(ValueError):
            lib.pair("barrage", {"R": "corner-fortress", "B": "corner-fortress"}, random.Random(0))
        with self.assertRaises(ValueError):
            lib.pair("barrage", {"R": "nope"}, random.Random(0))

    def test_validate_deployment_names_the_wrong_rank(self):
        dep, _ = lib.get("barrage", "R", "corner-fortress")
        dep = dict(dep)
        sq = next(s for s, r in dep.items() if r == "Scout")
        dep[sq] = "Bomb"
        with self.assertRaises(IllegalMove) as cm:
            validate_deployment(dep, "R", "barrage")
        self.assertEqual(cm.exception.kind, "deployment")
        self.assertIn("2x Bomb", str(cm.exception))
        self.assertIn("0x Scout", str(cm.exception))

    def test_random_deployment_is_legal(self):
        for variant in ("barrage", "classic"):
            validate_deployment(random_deployment("B", variant, random.Random(1)), "B", variant)


class Observation(unittest.TestCase):
    def test_names_the_lakes_and_says_the_list_is_complete(self):
        obs = render(position(), "R")
        self.assertIn("LAKES (impassable, always empty): c5 c6 d5 d6 g5 g6 h5 h6", obs)
        self.assertIn("this list is complete", obs)
        self.assertIn("YOUR PIECES: d4=Scout", obs)

    def test_threats_follow_the_legal_move_list(self):
        r, _ = lib.get("barrage", "R", "corner-fortress")
        b, _ = lib.get("barrage", "B", "corner-fortress")   # mirror on purpose: Marshals meet
        st = GameState.from_deployments(r, b, variant="barrage", move_cap=60)
        st.apply(Move("e4", "e5"))
        st.apply(Move("e7", "e6"))
        obs = render(st, "R")
        self.assertIn("e5 Marshal <- e6(?)", obs)
        self.assertLess(obs.index("LEGAL MOVES"), obs.index("THREATS"))

    def test_fog_and_public_facts(self):
        st = position()
        st.apply(Move("d4", "d1"))            # a Scout moved >1 square
        obs = render(st, "B")
        self.assertIn("d1: moved >1 square, so it is a Scout", obs)
        enemy = obs.split("ENEMY PIECES (")[1].split("ENEMY STILL HAS")[0]
        self.assertNotIn("Marshal", enemy)    # unrevealed ranks never leak


if __name__ == "__main__":
    unittest.main()
