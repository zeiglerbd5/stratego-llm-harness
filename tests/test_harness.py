"""The harness around the engine: token accounting, the retry loop, Match
scoring, and metrics over real Game Records. No network: the Model is stubbed.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

import stratego.agent as A
from stratego import deployments as lib
from stratego.adapter import Completion, ModelProfile, _thinking_tokens
from stratego.game import GameState
from stratego.match import aggregate
from stratego.metrics import analyze

ROOT = Path(__file__).resolve().parent.parent


class ThinkingTokens(unittest.TestCase):
    cloud = ModelProfile("x", base_url="https://example.invalid/v1", context_tokens=None)

    def test_provider_count_wins(self):
        usage = {"completion_tokens": 900, "completion_tokens_details": {"reasoning_tokens": 800}}
        self.assertEqual(_thinking_tokens(self.cloud, usage, "trace"), (800, "provider"))

    def test_no_trace_is_none(self):
        self.assertEqual(_thinking_tokens(self.cloud, {"completion_tokens": 50}, ""), (0, "none"))

    def test_cloud_without_a_count_is_a_labelled_estimate(self):
        n, src = _thinking_tokens(self.cloud, {"completion_tokens": 50}, "x" * 300)
        self.assertEqual(src, "estimate")
        self.assertEqual(n, 100)

    def test_budget_exhausted_means_length_with_nothing_returned(self):
        self.assertTrue(Completion("", "long trace", "length", 10, 4000, 1.0).budget_exhausted)
        self.assertFalse(Completion('{"x":1', "t", "length", 10, 4000, 1.0).budget_exhausted)
        self.assertFalse(Completion("", "", "stop", 10, 4, 1.0).budget_exhausted)


class RetryLoop(unittest.TestCase):
    """An illegal Move, then a parse failure, then a legal Move: every attempt
    is recorded with its kind, and thinking is summed across all three."""

    def setUp(self):
        self.replies = [
            ('{"rationale":"x","from":"d4","to":"d5","scratchpad":"s"}', 300, "tokenizer"),
            ("not json", 0, "none"),
            ('{"rationale":"ok","from":"d4","to":"d3","scratchpad":"plan"}', 250, "estimate"),
        ]
        self.real = A.complete
        A.complete = self.fake

    def tearDown(self):
        A.complete = self.real

    def fake(self, profile, messages, schema, thinking="standard", max_tokens=None, timeout=600):
        content, think, src = self.replies.pop(0)
        return Completion(content, "trace", "stop", 1500, 110, 5.0, think, src)

    def test_attempts_and_totals(self):
        r, _ = lib.get("barrage", "R", "far-corner")
        b, _ = lib.get("barrage", "B", "centre-guard")
        st = GameState.from_deployments(r, b, variant="barrage", move_cap=60)
        turn = A.Agent("red:stub", ModelProfile("stub"), "R", "brief").choose_move(st)
        self.assertEqual(str(turn.move), "d4-d3")
        self.assertIsNone(turn.failure)
        self.assertEqual([a.get("error_kind") for a in turn.attempts], ["lake", None, None])
        self.assertEqual([a.get("failure") for a in turn.attempts], ["illegal_move", "parse_failure", None])
        self.assertEqual(turn.thinking_tokens, 550)
        self.assertEqual(turn.thinking_tokens_source, "estimate")   # least trustworthy attempt wins
        self.assertEqual(turn.completion_tokens, 330)
        self.assertEqual(turn.scratchpad, "plan")

    def test_parse_accepts_a_fenced_block(self):
        comp = Completion('```json\n{"from":"a1","to":"a2"}\n```', "", "stop", 1, 1, 0.1)
        self.assertEqual(A.Agent._parse(comp), {"from": "a1", "to": "a2"})


class MatchScoring(unittest.TestCase):
    def game(self, tag, adjudicated, rej_r=None, rej_b=None):
        side = lambda rej: {"moves": 30, "shuffle_rate": 0.1, "thinking_tokens": 100,
                            "rejections": rej or {}, "thinking_tokens_source": "provider"}
        return {"tag": tag, "adjudicated": adjudicated,
                "per_side": {"R": side(rej_r), "B": side(rej_b)}}

    def test_scored_by_seat_not_by_name(self):
        games = [self.game("p0a", "R", rej_r={"lake": 1}),   # a is Red and wins
                 self.game("p0b", "R"),                        # b is Red and wins
                 self.game("p1a", "draw")]
        rep = aggregate(games, "same", "same")
        self.assertEqual(rep["by_model"]["a"], {"wins": 1, "losses": 1, "draws": 1, "games": 3})
        self.assertEqual(rep["by_model"]["b"], {"wins": 1, "losses": 1, "draws": 1, "games": 3})
        self.assertEqual(rep["by_color"], {"R": 2, "B": 0, "draw": 1})
        self.assertEqual(rep["rejections"]["a"], {"lake": 1})
        self.assertNotIn("thinking_tokens_source", rep["means"]["a"])


class RealRecords(unittest.TestCase):
    """Metrics replay committed Game Records and must reproduce their outcomes."""

    def record(self, rel):
        p = ROOT / rel
        if not p.exists():
            self.skipTest(f"{rel} not present")
        return p

    def test_barrage_flag_capture(self):
        a = analyze(self.record("records/match-sonnet5-vs-terra-standard/p0a.jsonl"))
        self.assertEqual((a["played_result"], a["played_reason"], a["plies"]), ("B", "flag_captured", 86))
        self.assertEqual(a["per_side"]["B"]["thinking_tokens_source"], "provider")
        self.assertEqual(a["failures"]["illegal_move"], 0)

    def test_classic_game(self):
        a = analyze(self.record("records/classic-sonnet5-vs-terra/g1.jsonl"))
        self.assertEqual(a["material"], {"R": 96, "B": 27})
        self.assertEqual(a["deployment_source"], "file")
        self.assertEqual(a["per_side"]["R"]["combat_won"], 22)

    def test_adjudicated_draw_reads_back(self):
        a = analyze(self.record("records/match-gptoss-brief/p2a.jsonl"))
        self.assertEqual(a["played_result"], "draw")
        self.assertEqual(a["adjudicated_result"], "R")
        self.assertIn("material +4", a["adjudicated_reason"])

    def test_every_committed_record_is_replayable(self):
        files = sorted((ROOT / "records").rglob("*.jsonl"))
        self.assertGreater(len(files), 20)
        for f in files:
            a = analyze(f)
            end = json.loads(f.read_text(encoding="utf-8").strip().splitlines()[-1])
            self.assertEqual(a["material"], end["material"], f.name)


if __name__ == "__main__":
    unittest.main()
