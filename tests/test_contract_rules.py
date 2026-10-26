"""Contract accounting acceptance fixtures; no game files or network required."""

import importlib.util
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
SPEC = importlib.util.spec_from_file_location("outlands_contract_rules", Path(__file__).resolve().parents[1] / "tools/contract_rules.py")
RULES = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = RULES
SPEC.loader.exec_module(RULES)


class ContractRulesTests(unittest.TestCase):
    def test_seeded_deck_rotates_with_equal_tasks_for_both_teams(self):
        self.assertEqual([RULES.phase_kind("dom", phase, 0) for phase in range(1, 7)], list(RULES.KINDS) * 2)
        self.assertEqual([RULES.phase_kind("tdm", phase, 0) for phase in range(1, 5)], list(RULES.KINDS[:2]) * 2)
        self.assertEqual(RULES.phase_kind("dom", 1, -10), RULES.phase_kind("dom", 1, 0))
        self.assertEqual(RULES.phase_kind("dom", 1, 999999), RULES.phase_kind("dom", 1, 9999))
        for mode in ("dm", "sd", "custom"):
            with self.assertRaises(ValueError):
                RULES.phase_kind(mode, 1)

    def test_goal_bounds_and_mode_specific_team_points(self):
        self.assertEqual(RULES.goal("dom", "team_eliminations", 0), 3)
        self.assertEqual(RULES.goal("dom", "combined_score", 9999), 4000)
        self.assertEqual(RULES.goal("ctf", "team_points", 25), 1)
        self.assertEqual(RULES.goal("dem", "team_points"), 1)
        self.assertEqual(RULES.goal("conf", "team_points"), 6)
        self.assertEqual(RULES.goal("koth", "team_points"), 12)
        with self.assertRaises(ValueError):
            RULES.goal("tdm", "team_points")

    def test_first_observation_and_new_occupant_do_not_award_old_counters(self):
        ledger = RULES.CounterLedger()
        ledger.observe({1: RULES.Sample("first", "allies", 50, 5000)}, {"allies": 80})
        self.assertEqual(sum(ledger.totals["allies"].values()), 0)
        ledger.observe({1: RULES.Sample("first", "allies", 52, 5200)}, {"allies": 82})
        self.assertEqual(ledger.totals["allies"], dict(zip(RULES.KINDS, (2, 200, 2))))
        ledger.observe({1: RULES.Sample("replacement", "allies", 80, 8000)}, {"allies": 82})
        self.assertEqual(ledger.totals["allies"], dict(zip(RULES.KINDS, (2, 200, 2))))

    def test_team_switch_and_departure_cannot_transfer_score(self):
        ledger = RULES.CounterLedger()
        ledger.observe({1: RULES.Sample("player", "allies", 10, 1000)}, {})
        ledger.observe({1: RULES.Sample("player", "axis", 11, 1100)}, {})
        ledger.observe({}, {})
        self.assertEqual(sum(ledger.totals["allies"].values()), 0)
        self.assertEqual(sum(ledger.totals["axis"].values()), 0)
        ledger.observe({1: RULES.Sample("player", "axis", 12, 1200)}, {})
        self.assertEqual(ledger.totals["axis"]["team_eliminations"], 1)

    def test_counter_resets_rebase_without_duplicate_credit(self):
        ledger = RULES.CounterLedger()
        ledger.observe({1: RULES.Sample("p", "allies", 10, 1000)}, {"allies": 10})
        ledger.observe({1: RULES.Sample("p", "allies", 12, 1200)}, {"allies": 12})
        ledger.observe({1: RULES.Sample("p", "allies", 0, 0)}, {"allies": 0})
        self.assertEqual(ledger.totals["allies"], dict(zip(RULES.KINDS, (2, 200, 2))))
        ledger.observe({1: RULES.Sample("p", "allies", 1, 100)}, {"allies": 1})
        self.assertEqual(ledger.totals["allies"], dict(zip(RULES.KINDS, (3, 300, 3))))
        self.assertEqual(ledger.rebases["allies"], 2)

    def test_score_penalty_and_kill_reset_rebase_metrics_independently(self):
        ledger = RULES.CounterLedger()
        ledger.observe({1: RULES.Sample("p", "allies", 10, 1000)}, {})
        # A scoreboard penalty cannot erase a separately observed elimination.
        ledger.observe({1: RULES.Sample("p", "allies", 11, 900)}, {})
        self.assertEqual(ledger.totals["allies"]["team_eliminations"], 1)
        self.assertEqual(ledger.totals["allies"]["combined_score"], 0)
        # A kill counter reset cannot manufacture eliminations; independently
        # observed positive scoreboard growth still remains valid score.
        ledger.observe({1: RULES.Sample("p", "allies", 0, 1000)}, {})
        self.assertEqual(ledger.totals["allies"]["team_eliminations"], 1)
        self.assertEqual(ledger.totals["allies"]["combined_score"], 100)
        self.assertEqual(ledger.rebases["allies"], 2)

    def test_impossible_samples_and_jumps_fail_closed(self):
        ledger = RULES.CounterLedger()
        ledger.observe({1: RULES.Sample("p", "allies", 0, 0)}, {"allies": 0})
        ledger.observe({1: RULES.Sample("p", "allies", 257, 100)}, {"allies": 1001})
        self.assertEqual(sum(ledger.totals["allies"].values()), 0)
        self.assertEqual(ledger.invalid["allies"], 2)
        ledger.observe({1: RULES.Sample("p", "allies", -1, 0)}, {"allies": -1})
        ledger.observe({1: RULES.Sample("p", "allies", 999, 9999)}, {"allies": 9999})
        self.assertEqual(sum(ledger.totals["allies"].values()), 0)

    def test_pause_discards_disabled_interval_without_resetting_match_commendations(self):
        ledger = RULES.CounterLedger()
        ledger.observe({1: RULES.Sample("p", "allies", 0, 0)}, {"allies": 0})
        ledger.observe({1: RULES.Sample("p", "allies", 2, 200)}, {"allies": 2})
        ledger.pause()
        ledger.observe({1: RULES.Sample("p", "allies", 20, 2000)}, {"allies": 20})
        self.assertEqual(ledger.totals["allies"], dict(zip(RULES.KINDS, (2, 200, 2))))

    def test_completion_is_earned_once_and_cannot_reuse_old_phase_progress(self):
        contract = RULES.Contract(100, 3, 30, current=100)
        self.assertIsNone(contract.update(102, 10))
        self.assertEqual(contract.update(103, 12), "complete")
        self.assertIsNone(contract.update(106, 31))
        self.assertEqual(contract.commendations, 1)
        next_contract = RULES.Contract(106, 3, 60, current=106)
        self.assertIsNone(next_contract.update(106, 32))
        self.assertEqual(next_contract.progress, 0)
        self.assertEqual(next_contract.commendations, 0)

    def test_expiry_is_once_and_late_events_cannot_award_old_contract(self):
        contract = RULES.Contract(0, 3, 30)
        self.assertEqual(contract.update(2, 30), "expired")
        self.assertIsNone(contract.update(3, 32))
        self.assertFalse(contract.complete)
        self.assertEqual(contract.commendations, 0)
        # The deadline has no grace window; no event time is inferred between
        # the last poll and an observation exactly at/after the deadline.
        deadline = RULES.Contract(0, 3, 30)
        deadline.update(2, 28)
        self.assertEqual(deadline.update(3, 30), "expired")
        self.assertEqual(deadline.progress, 2)
        self.assertEqual(deadline.commendations, 0)
        self.assertEqual(RULES.Contract(0, 3, 30).update(3, 31), "expired")

    def test_new_match_has_no_counters_or_rewards_from_previous_match(self):
        old = RULES.Contract(0, 3, 30)
        old.update(3, 10)
        ledger, contract = RULES.CounterLedger(), RULES.Contract(0, 3, 30)
        self.assertEqual(sum(sum(row.values()) for row in ledger.totals.values()), 0)
        self.assertEqual(contract.commendations, 0)
        self.assertFalse(contract.complete)

    def test_host_preview_clamps_actual_runtime_settings_and_has_no_native_reward(self):
        stream = io.StringIO()
        with redirect_stdout(stream):
            status = RULES.main(["--mode", "ctf", "--seed", "-3", "--seconds", "1", "--goal-scale", "900", "--phases", "3"])
        report = json.loads(stream.getvalue())
        self.assertEqual(status, 0)
        self.assertEqual(report["settings"], {"outlands_contract_seed": 0, "outlands_contract_seconds": 30, "outlands_contract_goal_scale": 400})
        self.assertEqual([(row["kind"], row["goal"]) for row in report["phases"]],
                         [("team_eliminations", 48), ("combined_score", 4000), ("team_points", 4)])
        self.assertFalse(report["native_xp_or_score_writes"])


if __name__ == "__main__":
    unittest.main()
