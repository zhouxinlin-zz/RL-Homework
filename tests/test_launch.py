import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from server import launch


class LaunchTests(unittest.TestCase):
    def test_old_service_uses_a_fresh_port(self):
        with patch.object(launch, "port_available", side_effect=lambda port: port == 8767), \
             patch.object(launch, "healthy", return_value=False):
            self.assertEqual(launch.choose_port(8765), 8767)

    def test_compatible_service_is_reused(self):
        with patch.object(launch, "port_available", return_value=False), \
             patch.object(launch, "healthy", return_value=True):
            self.assertEqual(launch.choose_port(8765), 8765)

    def test_source_edits_trigger_frontend_rebuild(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "web/src/GameApp.tsx"
            source.parent.mkdir(parents=True)
            source.write_text("source", encoding="utf-8")
            self.assertTrue(launch.frontend_needs_build(root))
            index = root / "web/dist/index.html"
            index.parent.mkdir(parents=True)
            index.write_text("built", encoding="utf-8")
            os.utime(source, (100, 100))
            os.utime(index, (200, 200))
            self.assertFalse(launch.frontend_needs_build(root))
            os.utime(source, (300, 300))
            self.assertTrue(launch.frontend_needs_build(root))
