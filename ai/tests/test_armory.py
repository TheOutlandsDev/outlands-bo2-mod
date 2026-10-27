"""Armory production validator/storage/queue tests with fictional catalog data.

No game assets, human profiles, network services or native unlock claims.
"""
import copy
from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import armory as a


def catalog():
    items = {"rifle": a.Item("primary"), "smg": a.Item("primary"), "pistol": a.Item("secondary"),
             "frag": a.Item("lethal", 2), "flash": a.Item("tactical", 2), "beacon": a.Item("tactical"),
             "fast": a.Item("perk1"), "quiet": a.Item("perk1"), "tough": a.Item("perk2"),
             "aware": a.Item("perk3"), "quick": a.Item("perk2"), "light": a.Item("perk3")}
    items.update({card: a.Item("wildcard") for card in a.WILDCARDS})
    combinations = frozenset(frozenset(row) for row in (("optic",), ("grip",), ("silencer",),
                             ("optic", "grip"), ("optic", "silencer"), ("optic", "grip", "silencer")))
    return a.Catalog("fixture_v1", items, {"rifle": combinations, "smg": combinations,
                                             "pistol": frozenset({frozenset({"optic"}), frozenset({"silencer"}), frozenset({"optic", "silencer"})})})


def observation(**changes):
    cat = catalog()
    attachments = frozenset((weapon, attachment) for weapon, combinations in cat.combinations.items()
                            for combination in combinations for attachment in combination)
    return replace(a.Observation("abcd12", "session_1", "map_1", 4, 10000, cat.revision, 10,
                                  frozenset(cat.items), attachments, True, True, True), **changes)


def loadout():
    return {"primary": "rifle", "secondary": "pistol", "primary_attachments": ["optic", "grip"],
            "secondary_attachments": [], "perks": [["fast"], ["tough"], ["aware"]],
            "lethal": {"item": "frag", "count": 1}, "tactical": {"item": "flash", "count": 2},
            "wildcards": []}


class ValidatorTests(unittest.TestCase):
    def check(self, value=None, obs=None, cat=None, now=10000):
        return a.validate(loadout() if value is None else value, cat or catalog(), obs or observation(), now)

    def rejects(self, reason, value=None, obs=None, cat=None, now=10000):
        with self.assertRaisesRegex(a.Rejected, "^" + reason + "$"):
            self.check(value, obs, cat, now)

    def test_exact_ten_and_knife_only_and_input_copy(self):
        value = loadout()
        result = self.check(value)
        self.assertEqual(result.points, 10)
        value["perks"][0].clear()
        self.assertEqual(result.loadout["perks"][0], ["fast"])
        empty = {"primary": None, "secondary": None, "primary_attachments": [], "secondary_attachments": [],
                 "perks": [[], [], []], "lethal": {"item": None, "count": 0},
                 "tactical": {"item": None, "count": 0}, "wildcards": []}
        self.assertEqual(self.check(empty).points, 0)

    def test_no_rank_guess_or_unlocked_flag_in_untrusted_request(self):
        for name, value in (("unlocked", True), ("rank", 55), ("identity", "ffff"), ("slot", 0), ("points", 0)):
            request = loadout() | {name: value}
            self.rejects("class_schema", request)
        self.rejects("item_locked", obs=observation(unlocked_items=frozenset({"pistol"})))

    def test_native_allocation_below_ten_respected(self):
        self.rejects("allocation_exceeded", obs=observation(allocation=9))
        for maximum in (True, 0, 11, 10.0, "10"):
            self.rejects("catalog_unavailable", obs=observation(allocation=maximum))

    def test_create_a_class_feature_requires_explicit_native_unlock(self):
        for value in (False, None, 1, "true"):
            self.rejects("create_a_class_locked", obs=observation(can_customize=value))

    def test_missing_stale_future_and_changed_observation_rejected(self):
        for now in (9999, 15001, -1, True, 1.0):
            self.rejects("observation_stale", now=now)
        self.assertEqual(self.check(now=15000).points, 10)
        self.rejects("catalog_unavailable", obs=observation(catalog_revision="fixture_v2"))
        self.rejects("observation_stale", obs=observation(spawn=True))

    def test_bots_spectators_and_missing_identity_rejected(self):
        for change in ({"human": False}, {"human": 1}, {"playing": False}, {"playing": 1},
                       {"identity": "0"}, {"identity": "name"}, {"identity": ""},
                       {"session": "x;quit"}, {"map_epoch": ""}):
            self.rejects("human_session_required", obs=observation(**change))

    def test_schema_is_bounded_exact_and_rejects_type_confusion(self):
        for value in (None, [], "class", 1, True, {}):
            # None is the helper's default, so call the production function.
            with self.assertRaises(a.Rejected):
                a.validate(value, catalog(), observation(), 10000)
        for key, bad in (("primary", []), ("secondary", True), ("primary_attachments", "optic"),
                         ("primary_attachments", ["optic"] * 4), ("perks", [[], []]),
                         ("perks", ["fast", [], []]), ("perks", [["fast", "quiet", "third"], [], []]),
                         ("wildcards", ["overkill"] * 4), ("lethal", {"item": "frag", "count": True}),
                         ("tactical", {"item": None, "count": 1}), ("tactical", {"item": "flash", "count": 0}),
                         ("tactical", {"item": "flash", "count": 3}), ("lethal", {"item": "frag", "count": 1, "cost": 0})):
            self.rejects("class_schema", loadout() | {key: bad})

    def test_malicious_ids_cannot_enter_catalog_or_class(self):
        for bad in ("rifle;quit", "../rifle", "a" * 49, "RIFLE", "rifle\n", 'rifle"', "é"):
            self.rejects("class_schema", loadout() | {"primary": bad})
        self.rejects("unknown_item", loadout() | {"primary": "not_shipped"})
        self.rejects("wrong_slot", loadout() | {"primary": "pistol"})

    def test_duplicates_and_attachment_parent_checks(self):
        self.rejects("class_schema", loadout() | {"primary_attachments": ["optic", "optic"]})
        self.rejects("class_schema", loadout() | {"wildcards": ["overkill", "overkill"]})
        self.rejects("class_schema", loadout() | {"perks": [["fast", "fast"], [], []]})
        self.rejects("attachment_without_weapon", loadout() | {"primary": None})

    def test_secondary_requires_earned_overkill_for_primary_weapon(self):
        value = loadout() | {"secondary": "smg", "tactical": {"item": "flash", "count": 1}}
        self.rejects("wrong_slot", value)
        value["wildcards"] = ["overkill"]
        self.assertEqual(self.check(value).points, 10)
        self.rejects("item_locked", value, observation(unlocked_items=observation().unlocked_items - {"overkill"}))
        self.rejects("duplicate_weapon", value | {"secondary": "rifle"})
        self.rejects("wildcard_without_item", value | {"secondary": None})

    def test_perk_greed_stays_in_its_slot_and_costs_a_point(self):
        value = loadout() | {"perks": [["fast", "quiet"], [], ["aware"]], "tactical": {"item": "flash", "count": 1}}
        self.rejects("wildcard_required", value)
        value["wildcards"] = ["perk_1_greed"]
        self.assertEqual(self.check(value).points, 10)
        self.rejects("wrong_slot", value | {"perks": [["fast", "tough"], [], ["aware"]]})
        self.rejects("allocation_exceeded", value | {"tactical": {"item": "flash", "count": 2}})

    def test_primary_and_secondary_gunfighter_counts(self):
        value = loadout() | {"primary_attachments": ["optic", "grip", "silencer"], "perks": [[], [], ["aware"]]}
        self.rejects("wildcard_required", value)
        value["wildcards"] = ["primary_gunfighter"]
        self.assertEqual(self.check(value).points, 10)
        second = loadout() | {"secondary_attachments": ["optic", "silencer"], "perks": [[], [], []]}
        self.rejects("wildcard_required", second)
        second["wildcards"] = ["secondary_gunfighter"]
        self.assertEqual(self.check(second).points, 10)
        self.rejects("wildcard_without_item", second | {"secondary": None, "secondary_attachments": []})

    def test_attachment_compatibility_including_triples_and_weapon_unlocks(self):
        self.rejects("attachment_conflict", loadout() | {"primary_attachments": ["grip", "silencer"]})
        self.rejects("attachment_locked", obs=observation(unlocked_attachments=observation().unlocked_attachments - {("rifle", "grip")}))
        self.rejects("attachment_conflict", loadout() | {"primary_attachments": ["unknown_attachment"]})
        cat = catalog()
        cat.combinations["rifle"] -= {frozenset({"optic", "grip", "silencer"})}
        value = loadout() | {"primary_attachments": ["optic", "grip", "silencer"], "perks": [[], [], []], "wildcards": ["primary_gunfighter"]}
        self.rejects("attachment_conflict", value, cat=cat)

    def test_equipment_and_wildcard_limits(self):
        value = loadout() | {"lethal": {"item": "frag", "count": 2}, "perks": [[], [], ["aware"]]}
        self.rejects("wildcard_required", value)
        value["wildcards"] = ["danger_close"]
        self.assertEqual(self.check(value).points, 10)
        self.rejects("wildcard_without_item", value | {"lethal": {"item": None, "count": 0}})
        self.rejects("equipment_count", loadout() | {"tactical": {"item": "beacon", "count": 2}})
        self.rejects("unsupported_wildcard", loadout() | {"wildcards": ["tactician"]})
        self.rejects("unknown_wildcard", loadout() | {"wildcards": ["invented"]})

    def test_missing_malformed_and_unbounded_native_catalog_fail_closed(self):
        for cat in (a.Catalog("", {}, {}), a.Catalog("a", {"rifle": a.Item("unknown")}, {}),
                    a.Catalog("a", {"rifle": a.Item("primary", 2)}, {}),
                    a.Catalog("a", {"rifle": a.Item("primary")}, {"pistol": frozenset()}),
                    a.Catalog("a", {"rifle": a.Item("primary")}, {"rifle": frozenset({frozenset()})})):
            self.rejects("catalog_unavailable", cat=cat)
        self.rejects("observation_invalid", obs=observation(unlocked_items=frozenset({"invented"})))
        self.rejects("observation_invalid", obs=observation(unlocked_items=set(catalog().items)))
        self.rejects("observation_invalid", obs=observation(unlocked_attachments=frozenset({("unknown", "optic")})))


@unittest.skipIf(os.name == "nt", "Private store runs on the Linux host; validator remains portable")
class StoreQueueTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)
        self.path = self.root / "armory.json"
        self.store = a.ArmoryStore(self.path)
        self.obs = observation()
        self.cat = catalog()
        self.queue = a.RespawnQueue(self.store, self.cat)

    def save(self, value=None, expected=0, request="save1", obs=None):
        return self.store.save(obs or self.obs, self.cat, value or loadout(), expected, request, 10000)

    def test_save_restart_private_identity_and_copy_isolation(self):
        record = self.save()
        self.assertEqual(record["revision"], 1)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        raw = self.path.read_text()
        self.assertNotIn(self.obs.identity, raw)
        self.assertNotIn(self.obs.session, raw)
        self.assertNotIn(self.obs.map_epoch, raw)
        self.assertEqual(a.ArmoryStore(self.path).read(self.obs.identity), record)
        self.assertEqual(self.store.read(self.obs.identity.upper()), record)
        self.assertIsNone(self.store.read("fff1"))
        record["loadout"]["perks"][0].clear()
        self.assertEqual(self.store.read(self.obs.identity)["loadout"]["perks"][0], ["fast"])

    def test_idempotent_retry_compare_and_swap_and_rejection_preserve_bytes(self):
        first = self.save()
        raw = self.path.read_bytes()
        self.assertEqual(self.save(), first)
        with self.assertRaisesRegex(a.Rejected, "request_conflict"):
            self.save(expected=1)
        with self.assertRaisesRegex(a.Rejected, "request_conflict"):
            self.save(loadout() | {"primary_attachments": []})
        for expected in (0, True, -1, a.MAX_REVISION):
            with self.assertRaises(a.Rejected):
                self.save(expected=expected, request="different")
            self.assertEqual(self.path.read_bytes(), raw)
        with self.assertRaises(a.Rejected):
            self.save(loadout() | {"primary": "not_shipped"}, expected=1)
        self.assertEqual(self.path.read_bytes(), raw)
        next_record = self.save(loadout() | {"primary_attachments": ["optic"]}, expected=1, request="save2")
        self.assertEqual(next_record["revision"], 2)

    def test_cross_player_cannot_queue_another_players_slot(self):
        self.save()
        other = replace(self.obs, identity="fff1", session="other_session")
        with self.assertRaisesRegex(a.Rejected, "revision_conflict"):
            self.queue.enqueue(other, 1, 10000)
        self.assertIsNone(self.queue.claim(other, 10000))
        self.assertEqual(self.save(obs=other)["revision"], 1)
        self.assertEqual(len(self.store.state["players"]), 2)

    def test_queue_current_life_does_nothing_next_spawn_claims_once(self):
        self.save()
        ticket = self.queue.enqueue(self.obs, 1, 10000)
        self.assertEqual(self.queue.enqueue(self.obs, 1, 10000), ticket)
        self.assertIsNone(self.queue.claim(self.obs, 10000))
        spawned = replace(self.obs, spawn=5)
        result = self.queue.claim(spawned, 10000)
        self.assertEqual(result["status"], "claimed_not_applied")
        self.assertEqual(result["loadout"], loadout())
        self.assertIsNone(self.queue.claim(spawned, 10000))
        self.assertIsNone(self.queue.claim(replace(spawned, spawn=6), 10000))
        with self.assertRaisesRegex(a.Rejected, "revision_already_claimed"):
            self.queue.enqueue(spawned, 1, 10000)
        restarted = a.RespawnQueue(a.ArmoryStore(self.path), self.cat)
        with self.assertRaisesRegex(a.Rejected, "revision_already_claimed"):
            restarted.enqueue(spawned, 1, 10000)
        # A reconnect needs explicit requeue and a fresh native observation.
        reconnected = replace(spawned, session="new_session")
        self.queue.enqueue(reconnected, 1, 10000)
        self.assertIsNotNone(self.queue.claim(replace(reconnected, spawn=6), 10000))

    def test_failed_consume_never_returns_a_class_or_leaves_pending_work(self):
        self.save()
        self.queue.enqueue(self.obs, 1, 10000)
        raw = self.path.read_bytes()
        with patch.object(a.os, "replace", side_effect=OSError("synthetic disk full")):
            with self.assertRaises(OSError):
                self.queue.claim(replace(self.obs, spawn=5), 10000)
        self.assertFalse(self.queue.pending)
        self.assertEqual(self.path.read_bytes(), raw)
        # Nothing was handed to an adapter, so an explicit retry can be queued.
        self.queue.enqueue(replace(self.obs, spawn=5), 1, 10000)
        self.assertIsNotNone(self.queue.claim(replace(self.obs, spawn=6), 10000))

    def test_committed_claim_survives_process_loss_without_raw_session_storage(self):
        self.save()
        self.queue.enqueue(self.obs, 1, 10000)
        claimed = self.queue.claim(replace(self.obs, spawn=5), 10000)
        self.assertEqual(claimed["status"], "claimed_not_applied")
        reopened = a.ArmoryStore(self.path)
        restarted = a.RespawnQueue(reopened, self.cat)
        with self.assertRaisesRegex(a.Rejected, "revision_already_claimed"):
            restarted.enqueue(replace(self.obs, spawn=5), 1, 10000)
        self.assertNotIn(self.obs.session, self.path.read_text())
        self.assertNotIn(self.obs.map_epoch, self.path.read_text())
        # A duplicate save acknowledgement cannot undo the durable claim.
        reopened.save(self.obs, self.cat, loadout(), 0, "save1", 10000)
        with self.assertRaisesRegex(a.Rejected, "revision_already_claimed"):
            restarted.enqueue(replace(self.obs, spawn=5), 1, 10000)

    def test_newest_accepted_revision_replaces_pending_once(self):
        self.save()
        self.queue.enqueue(self.obs, 1, 10000)
        second = self.save(loadout() | {"primary_attachments": []}, expected=1, request="save2")
        self.queue.enqueue(self.obs, second["revision"], 10000)
        self.assertEqual(self.queue.claim(replace(self.obs, spawn=5), 10000)["revision"], 2)

    def test_saved_but_not_queued_revision_invalidates_older_ticket(self):
        self.save()
        self.queue.enqueue(self.obs, 1, 10000)
        self.save(expected=1, request="save2")
        with self.assertRaisesRegex(a.Rejected, "revision_conflict"):
            self.queue.claim(replace(self.obs, spawn=5), 10000)
        self.assertFalse(self.queue.pending)

    def test_disconnect_map_round_session_and_missed_spawn_cancel_pending(self):
        self.save()
        for changes in ({"session": "reconnect"}, {"map_epoch": "map_2"}, {"spawn": 3}, {"spawn": 6}, {"playing": False}, {"human": False}):
            self.queue.enqueue(self.obs, 1, 10000)
            with self.assertRaises(a.Rejected):
                self.queue.claim(replace(self.obs, **changes), 10000)
            self.assertFalse(self.queue.pending)
        self.queue.enqueue(self.obs, 1, 10000)
        self.queue.cancel(self.obs.identity)
        self.assertIsNone(self.queue.claim(replace(self.obs, spawn=5), 10000))
        self.queue.enqueue(self.obs, 1, 10000)
        restarted = a.RespawnQueue(a.ArmoryStore(self.path), self.cat)
        self.assertFalse(restarted.pending)
        self.assertEqual(restarted.store.read(self.obs.identity)["revision"], 1)

    def test_unlock_revalidation_at_spawn_and_staleness_do_not_apply(self):
        self.save()
        for changes in ({"unlocked_items": self.obs.unlocked_items - {"rifle"}},
                        {"unlocked_attachments": frozenset()}, {"allocation": 9},
                        {"observed_ms": 1}, {"catalog_revision": "changed"}, {"can_customize": False}):
            self.queue.enqueue(self.obs, 1, 10000)
            with self.assertRaises(a.Rejected):
                self.queue.claim(replace(self.obs, spawn=5, **changes), 10000)
            self.assertFalse(self.queue.pending)

    def test_failed_write_leaves_old_slot_and_no_temporary_file(self):
        self.save()
        raw = self.path.read_bytes()
        with patch.object(a.os, "replace", side_effect=OSError("synthetic disk full")):
            with self.assertRaises(OSError):
                self.save(expected=1, request="save2")
        self.assertEqual(self.path.read_bytes(), raw)
        self.assertEqual(self.store.read(self.obs.identity)["revision"], 1)
        self.assertFalse(list(self.root.glob(".armory-*")))

    def test_post_rename_fsync_failure_requires_reload_before_ack_or_new_write(self):
        self.save()
        with patch.object(a.os, "fsync", side_effect=[None, OSError("synthetic directory flush failure")]):
            with self.assertRaises(OSError):
                self.save(expected=1, request="save2")
        with self.assertRaisesRegex(a.Rejected, "store_reload_required"):
            self.store.read(self.obs.identity)
        with self.assertRaisesRegex(a.Rejected, "store_reload_required"):
            self.save(expected=1, request="save3")
        restored = a.ArmoryStore(self.path)
        self.assertEqual(restored.read(self.obs.identity)["revision"], 2)
        self.assertEqual(restored.save(self.obs, self.cat, loadout(), 1, "save2", 10000)["revision"], 2)
        self.assertFalse(list(self.root.glob(".armory-*")))

    def test_permissive_links_and_corrupt_state_are_rejected(self):
        self.save()
        self.path.chmod(0o644)
        with self.assertRaises(a.Rejected):
            a.ArmoryStore(self.path)
        self.path.chmod(0o600)
        link = self.root / "linked.json"
        link.symlink_to(self.path)
        with self.assertRaises((a.Rejected, OSError)):
            a.ArmoryStore(link)
        hardlink = self.root / "hard.json"
        os.link(self.path, hardlink)
        with self.assertRaises(a.Rejected):
            a.ArmoryStore(hardlink)
        hardlink.unlink()
        original = json.loads(self.path.read_text())
        for bad in (original | {"schema": True}, original | {"salt": "invalid"}, original | {"extra": 1}):
            with self.assertRaises(a.Rejected):
                a.ArmoryStore.check(bad)
        original["players"][next(iter(original["players"]))]["loadout"]["primary"] = "smg"
        with self.assertRaises(a.Rejected):
            a.ArmoryStore.check(original)


if __name__ == "__main__":
    unittest.main()
