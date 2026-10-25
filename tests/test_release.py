"""Release assurance using copied public text sources and synthetic private files only."""

from contextlib import redirect_stderr, redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile
import unittest
from unittest.mock import patch
import zipfile

sys.dont_write_bytecode = True
SOURCE = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("outlands_release", SOURCE / "tools/build_release.py")
RELEASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RELEASE)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="outlands-release-test-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.root = self.directory / "Source Clone With Spaces"
        for name in RELEASE.PUBLIC_PATHS:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(SOURCE / name, target)

    def snapshot(self):
        return {p.relative_to(self.root).as_posix():
                (p.stat().st_mode, p.stat().st_mtime_ns, p.read_bytes() if p.is_file() else None)
                for p in self.root.rglob("*")}

    def run_main(self, arguments, expected=0):
        output = io.StringIO()
        with patch.object(RELEASE, "ROOT", self.root), \
                patch.object(sys, "argv", ["build_release.py", *arguments]), \
                redirect_stdout(output), redirect_stderr(output):
            result = RELEASE.main()
        self.assertEqual(result, expected, output.getvalue())
        return output.getvalue()

    def test_explicit_manifest_excludes_private_game_and_unlisted_source_files(self):
        extras = ("t6mp.exe", "zone/all/game.ff", "runtime/client.json", "runtime/downloads/vendor.exe",
                  "hosting/.env", "hosting/host-settings.json", "hosting/private/server_key",
                  "hosting/logs/console.log", "hosting/package/info.json", "friend.invite.json",
                  "storage/t6/players/profile.stats", "tools/private_notes.py", "tests/private_test.py",
                  "docs/private.md", ".github/workflows/private.yml")
        for name in extras:
            path = self.root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b"\0synthetic private data")
        files = RELEASE.public_files(self.root)
        names = [p.relative_to(self.root).as_posix() for p in files]
        self.assertEqual(names, sorted(RELEASE.PUBLIC_PATHS))
        archive = self.directory / "release" / "source.zip"
        RELEASE.build_archive(archive, files, self.root)
        with zipfile.ZipFile(archive) as source:
            self.assertEqual(source.namelist(), [RELEASE.ARCHIVE_PREFIX + name for name in names])
        self.assertTrue({"CHANGELOG.md", "docs/RELEASING.md", ".github/workflows/ci.yml",
                         ".github/workflows/release.yml", "tests/test_windows_client.ps1"}
                        <= RELEASE.PUBLIC_PATHS)

    def test_archive_bytes_and_metadata_ignore_source_modes_mtimes_and_input_order(self):
        files = RELEASE.public_files(self.root)
        first = self.directory / "first build" / "outlands-bo2-mod-v0.1.1.zip"
        second = self.directory / "second build" / first.name
        digest = RELEASE.build_archive(first, files, self.root)
        for path in files:
            path.chmod(0o600 if path.suffix == ".sh" else 0o755)
            os.utime(path, (1700000000, 1700000000))
        self.assertEqual(RELEASE.build_archive(second, list(reversed(files)), self.root), digest)
        self.assertEqual(first.read_bytes(), second.read_bytes())
        self.assertEqual(digest, hashlib.sha256(first.read_bytes()).hexdigest())
        expected_sum = f"{digest}  {first.name}\n"
        self.assertEqual((first.parent / "SHA256SUMS").read_text(), expected_sum)
        self.assertEqual((second.parent / "SHA256SUMS").read_text(), expected_sum)
        with zipfile.ZipFile(first) as archive:
            self.assertIsNone(archive.testzip())
            self.assertEqual(archive.comment, b"")
            self.assertEqual(archive.namelist(), sorted(archive.namelist()))
            for info in archive.infolist():
                name = info.filename.removeprefix(RELEASE.ARCHIVE_PREFIX)
                self.assertIn(name, RELEASE.PUBLIC_PATHS)
                self.assertEqual(info.date_time, RELEASE.ZIP_TIMESTAMP)
                self.assertEqual(info.create_system, 3)
                self.assertEqual(info.external_attr >> 16,
                                 stat.S_IFREG | (0o755 if name.endswith(".sh") else 0o644))
                self.assertEqual(info.compress_type, zipfile.ZIP_DEFLATED)
                self.assertEqual(info.extra, b"")
                self.assertEqual(archive.read(info), (self.root / name).read_bytes())

    def test_audit_json_and_version_have_no_writes_and_json_preserves_source_bytes(self):
        readme = self.root / "README.md"
        readme.write_bytes(b"\xef\xbb\xbfPublic fixture\r\nSecond line\r\n")
        before = self.snapshot()
        self.assertIn("PASS:", self.run_main([]))
        version = RELEASE.release_version(self.root)
        self.assertEqual(self.run_main(["--version"]), version + "\n")
        records = json.loads(self.run_main(["--json"]))
        self.assertEqual([record["path"] for record in records], sorted(RELEASE.PUBLIC_PATHS))
        for record in records:
            path = self.root / record["path"]
            self.assertEqual(record["content"].encode("utf-8"), path.read_bytes())
            self.assertEqual(record["mode"], "100755" if path.suffix == ".sh" else "100644")
        self.assertEqual(self.snapshot(), before)

    def test_missing_required_files_fail_before_creating_release_output(self):
        for name in ("README.md", ".github/workflows/release.yml", "tests/test_windows_client.ps1"):
            with self.subTest(name=name):
                path = self.root / name
                raw = path.read_bytes()
                path.unlink()
                output = self.directory / "must not exist" / "source.zip"
                self.assertIn("Missing required public source", self.run_main(["--output", str(output)], 1))
                self.assertFalse(output.parent.exists())
                path.write_bytes(raw)

    def test_unsafe_source_bytes_and_private_development_data_are_rejected(self):
        path = self.root / "README.md"
        values = (b"synthetic\0binary", b"\xffnot utf8", b"x" * (RELEASE.MAX_SOURCE_BYTES + 1),
                  (".".join(("100", "64", "0", "1")) + ":4977").encode(),
                  ("/" + "home" + "/fixture/private.txt").encode())
        for raw in values:
            with self.subTest(kind=raw[:16]):
                path.write_bytes(raw)
                with self.assertRaises(ValueError):
                    RELEASE.public_files(self.root)

    @unittest.skipUnless(os.name == "posix", "Symlink cases run on Linux without Windows link privileges")
    def test_file_and_parent_symlinks_and_nonregular_files_are_rejected(self):
        readme = self.root / "README.md"
        raw = readme.read_bytes()
        readme.unlink()
        readme.symlink_to(self.root / "NOTICE.md")
        with self.assertRaisesRegex(ValueError, "link"):
            RELEASE.public_files(self.root)
        readme.unlink()
        readme.mkdir()
        with self.assertRaisesRegex(ValueError, "nonregular"):
            RELEASE.public_files(self.root)
        readme.rmdir()
        readme.write_bytes(raw)
        original = self.root / "docs"
        outside = self.directory / "Outside Docs"
        original.rename(outside)
        original.symlink_to(outside, target_is_directory=True)
        with self.assertRaisesRegex(ValueError, "link"):
            RELEASE.public_files(self.root)

    def test_existing_release_or_checksum_is_never_overwritten(self):
        files = RELEASE.public_files(self.root)
        output = self.directory / "release" / "v0.1.0.zip"
        RELEASE.build_archive(output, files, self.root)
        original = output.read_bytes()
        sums = (output.parent / "SHA256SUMS").read_bytes()
        for candidate in (output, output.parent / "v0.1.1.zip"):
            with self.assertRaisesRegex(ValueError, "already exists"):
                RELEASE.build_archive(candidate, files, self.root)
        self.assertEqual(output.read_bytes(), original)
        self.assertEqual((output.parent / "SHA256SUMS").read_bytes(), sums)
        self.assertFalse((output.parent / "v0.1.1.zip").exists())

    def test_invalid_archive_inputs_are_rejected_and_failed_build_cleans_up(self):
        files = RELEASE.public_files(self.root)
        output = self.directory / "new output" / "source.zip"
        for inputs in (files[:-1], files + [self.root / "README.md"]):
            with self.assertRaisesRegex(ValueError, "exactly match"):
                RELEASE.build_archive(output, inputs, self.root)
        self.assertFalse(output.parent.exists())
        for name in ("invalid.txt", "bad\nname.zip", "bad\\name.zip"):
            with self.assertRaisesRegex(ValueError, "filename"):
                RELEASE.build_archive(output.parent / name, files, self.root)
        self.assertFalse(output.parent.exists())
        with patch.object(zipfile.ZipFile, "writestr", side_effect=OSError("synthetic write failure")):
            with self.assertRaisesRegex(OSError, "synthetic write failure"):
                RELEASE.build_archive(output, files, self.root)
        self.assertFalse(output.exists())
        self.assertFalse((output.parent / "SHA256SUMS").exists())

    def test_version_accepts_release_and_prerelease_and_rejects_tag_or_multiline_input(self):
        path = self.root / "VERSION"
        for value in ("0.1.1", "0.1.1\n", "0.1.1\r\n", "0.1.1-rc.1\n"):
            path.write_bytes(value.encode())
            self.assertEqual(RELEASE.release_version(self.root), value.rstrip("\r\n"))
        for value in ("v0.1.1\n", "01.1.1\n", "0.1\n", "0.1.1 \n", "0.1.1\n\n", "../other", "x" * 129):
            path.write_text(value)
            self.assertIn("VERSION", self.run_main(["--version"], 1))


if __name__ == "__main__":
    unittest.main()
