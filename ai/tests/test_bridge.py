import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import sys
SPEC = importlib.util.spec_from_file_location("outlands_bridge", Path(__file__).resolve().parents[1] / "bridge.py")
bridge = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)
BASE = Path(__file__).resolve().parents[1]


def event(now=100, name="Scout", request="map1_42"):
    return bridge.Event.parse(f"OUTLANDS_CHAT_V1|{request}|3|{name}|reply|mp_raid|tdm|Player|nice round", now)


class ConfigTests(unittest.TestCase):
    def test_default_is_opt_in_and_check_does_not_enable(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertFalse(bridge.Config.load(BASE / "config.example.json").enabled)

    def test_only_explicit_one_enables(self):
        with patch.dict(os.environ, {"T6_CHAT_ENABLED": "1"}, clear=True):
            self.assertTrue(bridge.Config.load(BASE / "config.example.json").enabled)
        with patch.dict(os.environ, {"T6_CHAT_ENABLED": "yes"}, clear=True):
            with self.assertRaises(bridge.ConfigError):
                bridge.Config.load(BASE / "config.example.json")

    def test_limits_and_origins_are_validated(self):
        for field, value in (("queue_size", 100), ("timeout_seconds", 90),
                             ("max_message_chars", 121), ("max_per_minute", 7),
                             ("ollama_url", "http://user:secret@localhost:11434"),
                             ("ollama_url", "file:///etc/passwd")):
            with self.subTest(field=field, value=value), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "config.json"
                path.write_text(json.dumps({field: value}))
                with patch.dict(os.environ, {}, clear=True), self.assertRaises(bridge.ConfigError):
                    bridge.Config.load(path)


class BoundaryTests(unittest.TestCase):
    def test_event_requires_exact_marker_fields_and_bot_identity(self):
        valid = event()
        self.assertEqual(valid.bot_name, "Scout")
        self.assertEqual(valid.slot, 3)
        lines = ["Player: OUTLANDS_CHAT_V1|id|3|Scout|reply|mp_raid|tdm||hello",
                 "OUTLANDS_CHAT_V1|id|18|Scout|reply|mp_raid|tdm||hello",
                 "OUTLANDS_CHAT_V1|id;quit|3|Scout|reply|mp_raid|tdm||hello",
                 "OUTLANDS_CHAT_V1|id|3|Scout|command|mp_raid|tdm||hello",
                 "OUTLANDS_CHAT_V1|id|3|^1Scout|reply|mp_raid|tdm||hello",
                 "OUTLANDS_CHAT_V1|id|3|Scout|reply|mp_raid|tdm||hello|extra"]
        for line in lines:
            self.assertIsNone(bridge.Event.parse(line, 100), line)

    def test_human_context_is_bounded_and_not_used_as_prompt_instructions(self):
        item = bridge.Event.parse("OUTLANDS_CHAT_V1|id|3|Scout|reply|mp_raid|tdm|^1Player|" + "x" * 1000, 1)
        self.assertEqual(len(item.text), 240)
        self.assertEqual(item.speaker, "Player")

    def test_reply_removes_injection_color_controls_and_multiline(self):
        result = bridge.sanitize_reply('^1GG;quit "x"\\\x00\t \x1b[31mteam!\nsecond line')
        self.assertEqual(result, "GG quit x team!")
        packet = bridge.rcon_packet("x" * 32, event(), result)
        self.assertEqual(packet, b'\xff\xff\xff\xffrcon ' + b'x' * 32 + b' set outlands_chat_response "map1_42|3|Scout|GG quit x team!"')
        self.assertEqual(packet.count(b'"'), 2)
        self.assertNotIn(b';', packet)

    def test_structured_output_and_operator_impersonation_are_refused(self):
        for text in ("Player: hi", "```quit```", "/quit", "!kick all", "{json}",
                     "I am a human", "I'm an administrator", "I am the server owner", "I'm not a bot"):
            self.assertEqual(bridge.sanitize_reply(text), "", text)

    def test_direct_unsanitized_transport_input_is_rejected(self):
        with self.assertRaises(ValueError):
            bridge.rcon_packet("x" * 32, event(), 'hello";quit')

    def test_remote_rcon_is_refused(self):
        for host in ("203.0.113.1", "192.168.1.2", "0.0.0.0", "example.com"):
            with self.assertRaises(ValueError):
                bridge.RconSink(host, 4977, Path("unused"))
        bridge.RconSink("127.0.0.1", 4977, Path("unused"))

    def test_private_secret_and_symlink_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            secret = Path(directory) / "secret"
            secret.write_text("a" * 48 + "\n")
            secret.chmod(0o600)
            self.assertEqual(bridge.read_secret(secret), "a" * 48)
            secret.chmod(0o644)
            with self.assertRaises(bridge.ConfigError):
                bridge.read_secret(secret)
            secret.chmod(0o600)
            link = Path(directory) / "link"
            link.symlink_to(secret)
            with self.assertRaises(OSError):
                bridge.read_secret(link)


class RuntimeTests(unittest.TestCase):
    def test_queue_deduplicates_bounds_and_expires_without_transport(self):
        sent = []
        class Sink:
            def send(self, item, text):
                sent.append((item.request_id, text))
        worker = bridge.Worker(bridge.Config(), None, Sink(), None)
        lines = [f"OUTLANDS_CHAT_V1|id{index}|3|Scout|reply|mp_raid|tdm|Player|hi" for index in range(5)]
        worker.ingest(lines + [lines[-1]], 100)
        self.assertEqual([x.request_id for x in worker.queue], ["id3", "id4"])
        self.assertIsNone(worker.next_event(116))
        self.assertEqual(sent, [])
        self.assertFalse(worker.deliver(event(100), ("GG", "fallback"), 116))
        self.assertTrue(worker.deliver(event(120), ("GG", "fallback"), 121))
        self.assertEqual(sent, [("map1_42", "GG")])

    def test_rate_reservation_counts_failures_and_bot_cooldown(self):
        limiter = bridge.Limiter(bridge.Config(global_cooldown_seconds=10, bot_cooldown_seconds=90, max_per_minute=2))
        self.assertTrue(limiter.reserve(event(), 100))
        self.assertFalse(limiter.reserve(event(name="Rook"), 105))
        self.assertFalse(limiter.reserve(event(), 111))
        self.assertTrue(limiter.reserve(event(name="Rook"), 111))
        self.assertFalse(limiter.reserve(event(name="Ember"), 122))
        self.assertTrue(limiter.reserve(event(name="Ember"), 161))

    def test_tail_starts_at_eof_handles_partial_rotation_and_large_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "console.log"
            path.write_text("historical record\n")
            tail = bridge.LogTail(path)
            self.assertEqual(tail.poll(), [])
            with path.open("a") as stream:
                stream.write("new")
            self.assertEqual(tail.poll(), [])
            with path.open("a") as stream:
                stream.write(" record\n")
            self.assertEqual(tail.poll(), ["new record"])
            with path.open("a") as stream:
                stream.write("x" * 3000)
            self.assertEqual(tail.poll(), [])
            with path.open("a") as stream:
                stream.write("trailing fake marker\nreal\n")
            self.assertEqual(tail.poll(), ["real"])
            path.rename(path.with_suffix(".old"))
            path.write_text("new map record\n")
            self.assertEqual(tail.poll(), ["new map record"])

    def test_burst_is_dropped_instead_of_replayed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "console.log"
            path.touch()
            tail = bridge.LogTail(path)
            tail.poll()
            path.write_text("x" * 70000 + "\n")
            self.assertEqual(tail.poll(), [])
            with path.open("a") as stream:
                stream.write("fresh\n")
            self.assertEqual(tail.poll(), ["fresh"])

    def test_ollama_payload_is_bounded_and_fallback_works_without_service(self):
        personalities = bridge.Personalities(BASE / "personalities.json")
        generator = bridge.Generator(bridge.Config(), personalities)
        class FakeOpener:
            def open(inner, request, timeout):
                payload = json.loads(request.data)
                self.assertFalse(payload["stream"])
                self.assertFalse(payload["think"])
                self.assertEqual(payload["options"]["num_ctx"], 2048)
                self.assertEqual(payload["options"]["num_predict"], 48)
                self.assertNotIn("tools", payload)
                self.assertEqual(len(json.loads(payload["messages"][1]["content"])["recent_bot_lines"]), 4)
                return io.BytesIO(json.dumps({"message": {"content": "Good round!"}}).encode())
        generator.opener = FakeOpener()
        self.assertEqual(generator.generate(event(), ["old"] * 10), ("Good round!", "ollama"))
        generator.opener.open = lambda *a, **kw: (_ for _ in ()).throw(OSError("offline"))
        message, source = generator.generate(event(), [])
        self.assertEqual(source, "fallback")
        self.assertEqual(bridge.sanitize_reply(message), message)

    def test_oversized_model_response_is_not_accepted(self):
        generator = bridge.Generator(bridge.Config(fallback_on_error=False), bridge.Personalities(BASE / "personalities.json"))
        class LargeOpener:
            def open(self, *args, **kwargs):
                return io.BytesIO(b"x" * 70000)
        generator.opener = LargeOpener()
        self.assertEqual(generator.generate(event(), []), ("", "unavailable"))


if __name__ == "__main__":
    unittest.main()
