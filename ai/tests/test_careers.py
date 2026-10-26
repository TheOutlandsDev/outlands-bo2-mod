"""Synthetic private-state and protocol tests. No game assets/network needed."""
from dataclasses import replace
import io
import json
import os
from pathlib import Path
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch

BASE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BASE))
import bridge
import careers


def sample(seq=1, kind="hello", session="map_a_slot3_c1", alias="Trailblazer", slot=3,
           kills=0, deaths=0, score=0, map_name="mp_raid", mode="tdm"):
    return careers.CareerEvent.parse(wire(seq, kind, session, alias, slot, kills, deaths, score, map_name, mode), ROSTER)


def wire(seq=1, kind="hello", session="map_a_slot3_c1", alias="Trailblazer", slot=3,
         kills=0, deaths=0, score=0, map_name="mp_raid", mode="tdm"):
    return f"OUTLANDS_BOT_V1|{session}|{session}_{seq}|{kind}|{slot}|{alias}|{kills}|{deaths}|{score}|{map_name}|{mode}"


ROSTER = bridge.Personalities(BASE / "personalities.json").profiles


class PrivateStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "careers.json"
        self.store = careers.CareerStore(self.path, ROSTER)

    def tearDown(self):
        self.directory.cleanup()

    def reload(self):
        self.store = careers.CareerStore(self.path, ROSTER)
        return self.store

    def test_seed_is_stable_and_only_future_native_deltas_earn_career_xp(self):
        initial = self.store.apply(sample(kills=8, deaths=3, score=900))
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["earned_xp"], 0)
        self.store.apply(sample(seq=2, kind="snapshot", kills=10, deaths=4, score=1150))
        record = self.store.state["careers"]["Trailblazer"]
        self.assertEqual((record["kills"], record["deaths"], record["score"], record["earned_xp"]), (2, 1, 250, 450))
        self.assertEqual(self.reload().profile("Trailblazer"), initial)
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["earned_xp"], 450)

    def test_restart_duplicate_out_of_order_and_hello_refresh_never_reaward(self):
        hello = sample(kills=4, score=400)
        self.store.apply(hello)
        snapshot = sample(seq=3, kind="snapshot", kills=9, deaths=2, score=1000)
        self.store.apply(snapshot)
        expected = dict(self.store.state["careers"]["Trailblazer"])
        self.reload()
        self.store.apply(snapshot)
        self.store.apply(sample(seq=2, kind="snapshot", kills=7, deaths=1, score=700))
        for _ in range(3):
            self.assertEqual(self.store.apply(hello), self.store.profile("Trailblazer"))
        self.assertEqual(self.store.state["careers"]["Trailblazer"], expected)
        self.assertEqual(self.store.state["sessions"][hello.session]["sequence"], 3)
        self.assertEqual(self.store.state["sessions"][hello.session]["kills"], 9)

    def test_missing_hello_baselines_snapshot_and_late_original_hello_restores(self):
        self.store.apply(sample(seq=4, kind="snapshot", kills=15, deaths=4, score=1800))
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["earned_xp"], 0)
        self.assertIsNotNone(self.store.apply(sample()))
        self.store.apply(sample(seq=5, kind="snapshot", kills=16, deaths=4, score=1900))
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["earned_xp"], 200)

    def test_connection_token_prevents_same_slot_alias_reconnect_inheriting_counters(self):
        self.store.apply(sample())
        self.store.apply(sample(seq=2, kind="depart", kills=7, deaths=2, score=700))
        self.store.apply(sample(seq=3, kind="snapshot", kills=9, deaths=3, score=900))
        self.assertIsNone(self.store.apply(sample()))
        self.store.apply(sample(session="map_a_slot3_c2", kills=7, deaths=2, score=700))
        self.store.apply(sample(seq=2, session="map_a_slot3_c2", kind="snapshot", kills=8, deaths=3, score=800))
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["kills"], 8)
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["earned_xp"], 1600)

    def test_known_session_cannot_change_slot_alias_map_or_mode(self):
        self.store.apply(sample())
        before = self.path.read_bytes()
        for event in (sample(seq=2, kind="snapshot", slot=4, kills=10, score=1000),
                      sample(seq=2, kind="snapshot", alias="MossCircuit", kills=10, score=1000),
                      sample(seq=2, kind="snapshot", map_name="mp_slums", kills=10, score=1000),
                      sample(seq=2, kind="snapshot", mode="dom", kills=10, score=1000)):
            self.assertIsNone(self.store.apply(event))
        self.assertEqual(self.path.read_bytes(), before)

    def test_round_reset_signed_score_and_outlier_rebase_without_awards(self):
        self.store.apply(sample(kills=10, deaths=4, score=1200))
        self.store.apply(sample(seq=2, kind="snapshot", kills=0, deaths=0, score=-50))
        self.store.apply(sample(seq=3, kind="snapshot", kills=1, deaths=1, score=50))
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["earned_xp"], 200)
        self.store.apply(sample(seq=4, kind="snapshot", kills=900, deaths=1, score=900000))
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["earned_xp"], 200)
        self.store.apply(sample(seq=5, kind="snapshot", kills=901, deaths=2, score=900100))
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["earned_xp"], 400)

    def test_final_sample_closes_once_and_does_not_claim_match_win(self):
        self.store.apply(sample())
        end = sample(seq=2, kind="match_end", kills=3, deaths=2, score=350)
        self.store.apply(end)
        self.store.apply(end)
        item = self.reload().state["careers"]["Trailblazer"]
        self.assertEqual((item["observed_rounds"], item["kills"], item["earned_xp"]), (1, 3, 650))
        self.assertNotIn("wins", item)

    def test_restart_and_original_hello_never_present_stale_scoreboard_as_current(self):
        self.store.apply(sample())
        with patch.object(careers.time, "monotonic", return_value=100):
            self.store.apply(sample(seq=2, kind="snapshot", kills=3, score=300))
            self.assertIn("own_public_scoreboard", self.store.context("Trailblazer", "", "mp_raid", "tdm"))
        with patch.object(careers.time, "monotonic", return_value=160):
            self.assertIn("own_public_scoreboard", self.store.context("Trailblazer", "", "mp_raid", "tdm"))
        with patch.object(careers.time, "monotonic", return_value=161):
            self.assertNotIn("own_public_scoreboard", self.store.context("Trailblazer", "", "mp_raid", "tdm"))
        self.reload()
        self.store.apply(sample())
        self.assertNotIn("own_public_scoreboard", self.store.context("Trailblazer", "", "mp_raid", "tdm"))
        self.store.apply(sample(seq=2, kind="snapshot", kills=3, score=300))
        self.assertNotIn("own_public_scoreboard", self.store.context("Trailblazer", "", "mp_raid", "tdm"))
        self.store.apply(sample(seq=3, kind="snapshot", kills=4, score=400))
        self.assertIn("own_public_scoreboard", self.store.context("Trailblazer", "", "mp_raid", "tdm"))

    def test_sessions_and_retired_replay_cache_have_fixed_caps(self):
        with patch.object(careers, "MAX_SESSIONS", 2), patch.object(careers, "MAX_RETIRED", 3):
            for index in range(7):
                session = f"map_slot3_connection{index}"
                self.store.apply(sample(session=session))
                self.store.apply(sample(seq=2, kind="depart", session=session))
            self.assertEqual(len(self.store.state["sessions"]), 2)
            self.assertEqual(len(self.store.state["retired"]), 3)
            before = self.path.read_bytes()
            self.assertIsNone(self.store.apply(sample(session="map_slot3_connection4")))
            self.assertEqual(self.path.read_bytes(), before)

    def test_level_cap_and_social_memory_are_bot_only_and_never_store_text(self):
        self.store.apply(sample())
        item = self.store.state["careers"]["Trailblazer"]
        item["xp"] = careers.MAX_XP - 10
        self.store.apply(sample(seq=2, kind="snapshot", kills=1, score=100))
        self.assertEqual(self.store.profile("Trailblazer")["level"], 55)
        self.assertEqual(self.store.profile("Trailblazer")["prestige"], 10)
        self.assertTrue(self.store.record_exchange("Trailblazer", "MossCircuit"))
        self.assertFalse(self.store.record_exchange("Trailblazer", "HumanPrivateName"))
        self.assertFalse(self.store.record_exchange("Trailblazer", "Trailblazer"))
        self.assertNotIn("HumanPrivateName", self.path.read_text())
        self.assertNotIn("chat", self.path.read_text())
        self.assertEqual(self.reload().context("Trailblazer", "MossCircuit")["previous_bot_exchanges"], 1)

    def test_atomic_replace_preserves_old_valid_state_on_failure_and_private_modes(self):
        self.store.apply(sample())
        original = self.path.read_bytes()
        self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        with patch.object(careers.os, "replace", side_effect=OSError("synthetic storage failure")):
            with self.assertRaises(OSError):
                self.store.apply(sample(seq=2, kind="snapshot", kills=2, score=200))
        self.assertEqual(self.path.read_bytes(), original)
        self.assertEqual(list(self.path.parent.glob(".careers-*")), [])
        self.reload().apply(sample(seq=2, kind="snapshot", kills=2, score=200))
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["earned_xp"], 400)

    def test_corrupt_future_unknown_alias_or_public_state_fails_closed(self):
        self.store.apply(sample())
        original = self.path.read_text()
        broken = ["{broken", json.dumps({"schema_version": 99, "careers": {}}),
                  json.dumps({"schema_version": 1, "careers": {"HumanPrivateName": {}}})]
        for value in broken:
            self.path.write_text(value)
            with self.assertRaises(ValueError):
                self.reload()
            self.assertEqual(self.path.read_text(), value, "Corrupt state was silently replaced")
        self.path.write_text(original)
        self.path.chmod(0o644)
        with self.assertRaises(careers.CareerError):
            self.reload()

    def test_symlink_state_and_parent_and_public_directory_are_refused(self):
        target = self.path.parent / "target"
        target.write_text("private")
        target.chmod(0o600)
        self.path.symlink_to(target)
        with self.assertRaises(OSError):
            self.reload()
        self.path.unlink()
        link = self.path.parent / "linked"
        link.symlink_to(self.path.parent, target_is_directory=True)
        with self.assertRaises(careers.CareerError):
            careers.CareerStore(link / "other.json", ROSTER)
        self.path.parent.chmod(0o755)
        with self.assertRaises(careers.CareerError):
            self.reload()
        self.path.parent.chmod(0o700)

    def test_additive_schema_migration_preserves_earned_aggregate(self):
        self.store.apply(sample())
        self.store.apply(sample(seq=2, kind="snapshot", kills=2, score=200))
        data = json.loads(self.path.read_text())
        for key in ("sessions", "retired", "social"):
            del data[key]
        self.path.write_text(json.dumps(data))
        self.reload()
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["earned_xp"], 400)
        self.store.apply(sample(session="new_connection", kills=9, score=900))
        self.assertEqual(self.store.state["careers"]["Trailblazer"]["earned_xp"], 400)
        self.assertIn("sessions", json.loads(self.path.read_text()))


class CareerBoundaryTests(unittest.TestCase):
    def test_parser_rejects_human_alias_wrong_fields_controls_and_bad_numbers(self):
        self.assertIsNotNone(sample(score=-100))
        bad = [wire(alias="HumanPrivateName"), wire(slot=18), wire(seq=0), wire(seq=-1),
               wire(seq=2147483648), wire(kills=-1), wire(score=10000001), wire(kind="chat"),
               wire(map_name='mp_raid";quit'), wire(session="bad;session"),
               "Player: " + wire(), wire() + "|extra", wire().replace("|tdm", "|tdm\x00"),
               wire().replace("map_a_slot3_c1_1", "unrelated_1")]
        for line in bad:
            self.assertIsNone(careers.CareerEvent.parse(line, ROSTER), line)

    def test_fixed_profile_transport_cannot_become_a_command_or_human_stat_write(self):
        item = sample()
        profile = {"level": 12, "prestige": 2, "role": "support"}
        packet = bridge.profile_packet("x" * 32, item, profile)
        self.assertEqual(packet, b'\xff\xff\xff\xffrcon ' + b'x' * 32 + b' set outlands_bot_profile_response "map_a_slot3_c1_1|3|Trailblazer|12|2|support"')
        for invalid in (dict(profile, level=True), dict(profile, level=56), dict(profile, prestige=11),
                        dict(profile, role='support";quit'), dict(profile, extra="arbitrary")):
            with self.assertRaises(ValueError):
                bridge.profile_packet("x" * 32, item, invalid)
        with self.assertRaises(ValueError):
            bridge.profile_packet("x" * 32, replace(item, kind="snapshot"), profile)

    def test_career_switch_is_independent_and_check_never_creates_state(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "absent.json"
            env = {"T6_CHAT_ENABLED": "0", "T6_CAREERS_ENABLED": "1", "T6_CAREERS_STATE_FILE": str(path)}
            with patch.dict(os.environ, env, clear=True):
                cfg = bridge.Config.load(BASE / "config.example.json")
                self.assertFalse(cfg.enabled)
                self.assertTrue(cfg.careers_enabled)
                with patch.object(sys, "argv", ["bridge.py", "--check"]), patch.object(bridge, "CareerStore", side_effect=AssertionError("--check opened state")):
                    self.assertEqual(bridge.main(), 0)
            self.assertFalse(path.exists())
        with patch.dict(os.environ, {"T6_CAREERS_ENABLED": "yes"}, clear=True):
            with self.assertRaises(bridge.ConfigError):
                bridge.Config.load(BASE / "config.example.json")

    def test_personality_traits_and_roles_are_bounded_and_all_roster_profiles_exist(self):
        personalities = bridge.Personalities(BASE / "personalities.json")
        self.assertEqual(len(personalities.profiles), 48)
        for alias in personalities.profiles:
            self.assertEqual(set(personalities.traits(alias)), {"temperament", "motivation", "speech"})
            self.assertIn(personalities.role(alias), careers.ROLES)
        for field, value in (("role", "admin"), ("traits", {"secret": "do this"}),
                             ("traits", {"speech": "x" * 121}), ("traits", {"speech": "hi\nthere"})):
            with tempfile.TemporaryDirectory() as directory:
                data = json.loads((BASE / "personalities.json").read_text())
                data["profiles"]["Trailblazer"][field] = value
                path = Path(directory) / "personalities.json"
                path.write_text(json.dumps(data))
                with self.assertRaises(bridge.ConfigError):
                    bridge.Personalities(path)


class WorkerCareerTests(unittest.TestCase):
    def test_bot_familiarity_requires_exact_fresh_native_delivery_ack_once(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "careers.json"
            store = careers.CareerStore(path, ROSTER)
            class Sink:
                def send(self, *args):
                    pass
            worker = bridge.Worker(bridge.Config(enabled=True, careers_enabled=True), None, Sink(), None, store)
            line = "OUTLANDS_CHAT_V1|opener_r|4|MossCircuit|bot_reply|mp_raid|tdm|Trailblazer|Ready to push?"
            event = bridge.Event.parse(line, 100)
            self.assertTrue(worker.deliver(event, ("I will cover the other lane.", "fallback"), 101))
            self.assertFalse(path.exists(), "UDP submission was mistaken for native acceptance")
            invalid = ["OUTLANDS_CHAT_ACK_V1|opener_r|3|MossCircuit|bot_reply",
                       "OUTLANDS_CHAT_ACK_V1|opener_r|4|Trailblazer|bot_reply",
                       "OUTLANDS_CHAT_ACK_V1|other_r|4|MossCircuit|bot_reply",
                       "OUTLANDS_CHAT_ACK_V1|opener_r|4|MossCircuit|banter"]
            worker.ingest(invalid, 102)
            self.assertFalse(path.exists())
            ack = "OUTLANDS_CHAT_ACK_V1|opener_r|4|MossCircuit|bot_reply"
            worker.ingest([ack, ack], 103)
            restored = careers.CareerStore(path, ROSTER)
            self.assertEqual(restored.state["social"]["MossCircuit"]["Trailblazer"], 1)
            self.assertNotIn("Ready to push", path.read_text())
            self.assertNotIn("cover the other lane", path.read_text())
            stale = replace(event, request_id="stale_r", received_at=110)
            worker.deliver(stale, ("Sounds good.", "fallback"), 111)
            worker.ingest([ack.replace("opener_r", "stale_r")], 117)
            self.assertEqual(store.state["social"]["MossCircuit"]["Trailblazer"], 1)

    def test_ack_cache_is_bounded_identity_only_and_parser_rejects_injection(self):
        guard = bridge.Acknowledgments()
        event = bridge.Event.parse("OUTLANDS_CHAT_V1|opener_r|4|MossCircuit|bot_reply|mp_raid|tdm|Trailblazer|Ready to push?", 100)
        for index in range(30):
            guard.record(replace(event, request_id=f"opener{index}_r"), 101)
        self.assertEqual(len(guard.pending), 16)
        self.assertNotIn("Ready to push", repr(guard.pending))
        ack = bridge.ChatAck.parse("OUTLANDS_CHAT_ACK_V1|opener29_r|4|MossCircuit|bot_reply")
        self.assertEqual(guard.accept(ack, 102), ("Trailblazer", "MossCircuit"))
        self.assertIsNone(guard.accept(ack, 102))
        guard.prune(107)
        self.assertFalse(guard.pending)
        for line in ("Player: OUTLANDS_CHAT_ACK_V1|id|4|MossCircuit|bot_reply",
                     "OUTLANDS_CHAT_ACK_V1|id|18|MossCircuit|bot_reply",
                     "OUTLANDS_CHAT_ACK_V1|id|4|MossCircuit|bot_reply|extra",
                     "OUTLANDS_CHAT_ACK_V1|id|4|MossCircuit\nquit|bot_reply"):
            self.assertIsNone(bridge.ChatAck.parse(line))

    def test_careers_run_with_chat_off_commit_before_transport_and_retry_after_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "careers.json"
            store = careers.CareerStore(path, ROSTER)
            replies = []
            class Sink:
                def send_profile(inner, item, profile):
                    restored = careers.CareerStore(path, ROSTER)
                    self.assertIn(item.session, restored.state["sessions"], "Response preceded durable commit")
                    replies.append((item, profile))
                    raise OSError("synthetic lost response")
                def send(inner, *args):
                    self.fail("Chat was delivered while disabled")
            worker = bridge.Worker(bridge.Config(careers_enabled=True), None, Sink(), None, store)
            worker.ingest([wire(), "OUTLANDS_CHAT_V1|req|3|Trailblazer|reply|mp_raid|tdm|HumanSecret|human private text"], 100)
            self.assertEqual(len(replies), 1)
            self.assertEqual(len(worker.queue), 0)
            worker.ingest([wire(seq=2, kind="snapshot", kills=3, score=400)], 101)
            restarted = bridge.Worker(bridge.Config(careers_enabled=True), None, Sink(), None, careers.CareerStore(path, ROSTER))
            restarted.ingest([wire(), wire(seq=2, kind="snapshot", kills=3, score=400)], 102)
            self.assertEqual(len(replies), 2)
            self.assertEqual(restarted.careers.state["careers"]["Trailblazer"]["earned_xp"], 700)
            self.assertNotIn("HumanSecret", path.read_text())
            self.assertNotIn("human private text", path.read_text())

    def test_careers_off_ignores_bot_events_and_never_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "careers.json"
            store = careers.CareerStore(path, ROSTER)
            worker = bridge.Worker(bridge.Config(), None, None, None, store)
            worker.ingest([wire()], 100)
            self.assertIsNone(worker.careers)
            self.assertFalse(path.exists())

    def test_context_contains_only_own_scoreboard_and_bot_peer_counts(self):
        with tempfile.TemporaryDirectory() as directory:
            store = careers.CareerStore(Path(directory) / "careers.json", ROSTER)
            store.apply(sample())
            store.apply(sample(seq=2, kind="snapshot", kills=4, deaths=2, score=450))
            store.record_exchange("Trailblazer", "MossCircuit")
            context = store.context("Trailblazer", "MossCircuit", "mp_raid", "tdm")
            self.assertEqual(context["own_public_scoreboard"], {"kills": 4, "deaths": 2, "score": 450})
            self.assertEqual(context["previous_bot_exchanges"], 1)
            self.assertNotIn("previous_bot_exchanges", store.context("Trailblazer", "HumanSecret", "mp_raid", "tdm"))
            self.assertNotIn("own_public_scoreboard", store.context("Trailblazer", "MossCircuit", "mp_slums", "tdm"))
            self.assertEqual(store.context("HumanSecret"), {})
            personalities = bridge.Personalities(BASE / "personalities.json")
            generator = bridge.Generator(bridge.Config(), personalities)
            item = bridge.Event.parse("OUTLANDS_CHAT_V1|id|3|Trailblazer|banter|mp_raid|tdm|match|short context", 100)
            class Opener:
                def open(inner, request, timeout):
                    payload = json.loads(request.data)
                    data = json.loads(payload["messages"][1]["content"])
                    self.assertEqual(data["bot_context"], context)
                    self.assertEqual(data["personality_traits"], personalities.traits("Trailblazer"))
                    self.assertEqual([x["role"] for x in payload["messages"]], ["system", "user"])
                    self.assertNotIn("tools", payload)
                    return io.BytesIO(b'{"message":{"content":"Ready for another push."}}')
            generator.opener = Opener()
            self.assertEqual(generator.generate(item, [], context), ("Ready for another push.", "ollama"))


if __name__ == "__main__":
    unittest.main()
