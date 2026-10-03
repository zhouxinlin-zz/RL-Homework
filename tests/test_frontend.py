import json
import os
from pathlib import Path
import tempfile
import unittest

from server.frontend import input_files, snapshot
from server.launch import frontend_needs_build


class FrontendBuildTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.source = self.root / "web/src/game.ts"
        self.index = self.root / "web/dist/index.html"
        self.texture = self.root / "web/dist/car.glb"
        self.source.parent.mkdir(parents=True)
        self.index.parent.mkdir(parents=True)
        self.source.write_bytes(b"export const speed = 30;\n")
        self.index.write_bytes(b"<html>game</html>\n")
        self.texture.write_bytes(b"binary-model\r\n")
        self.manifest = self.root / "web/dist/build-info.json"
        self.manifest.write_text(json.dumps({
            "version": 1, "inputs": snapshot(self.root, input_files(self.root)),
            "outputs": snapshot(self.root, [self.index, self.texture]),
        }), encoding="utf-8")

    def test_checkout_times_and_windows_text_endings_do_not_require_node(self):
        os.utime(self.index, (100, 100))
        os.utime(self.source, (300, 300))
        self.source.write_bytes(self.source.read_bytes().replace(b"\n", b"\r\n"))
        self.assertFalse(frontend_needs_build(self.root))

    def test_source_change_is_detected_even_when_mtime_is_preserved(self):
        previous = self.source.stat()
        self.source.write_text("export const speed = 20;\n", encoding="utf-8")
        os.utime(self.source, ns=(previous.st_atime_ns, previous.st_mtime_ns))
        self.assertTrue(frontend_needs_build(self.root))

    def test_missing_source_or_output_triggers_rebuild(self):
        self.source.unlink()
        self.assertTrue(frontend_needs_build(self.root))
        self.source.write_bytes(b"export const speed = 30;\n")
        self.assertFalse(frontend_needs_build(self.root))
        self.texture.unlink()
        self.assertTrue(frontend_needs_build(self.root))

    def test_new_assets_and_binary_corruption_are_detected(self):
        added = self.source.parent / "new.ts"
        added.write_text("new source", encoding="utf-8")
        self.assertTrue(frontend_needs_build(self.root))
        added.unlink()
        self.texture.write_bytes(b"binary-model\n")
        self.assertTrue(frontend_needs_build(self.root))

    def test_malformed_manifest_does_not_crash_the_launcher(self):
        for contents in ("{", "[]", '{"version": 1}', '{"version": 999}'):
            with self.subTest(contents=contents):
                self.manifest.write_text(contents, encoding="utf-8")
                self.assertTrue(frontend_needs_build(self.root))
