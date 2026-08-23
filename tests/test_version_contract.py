import json
import re
import unittest
from pathlib import Path


class VersionContractTests(unittest.TestCase):
    def test_manifest_and_health_version_match(self):
        root = Path(__file__).resolve().parents[1]
        manifest = json.loads((root / "plugin.json").read_text(encoding="utf-8"))
        source = (root / "backend" / "main.py").read_text(encoding="utf-8")
        match = re.search(r'^PLUGIN_VERSION = "([^"]+)"$', source, re.MULTILINE)
        self.assertIsNotNone(match)
        self.assertEqual(match.group(1), manifest["version"])
        self.assertIn('"version": PLUGIN_VERSION', source)


if __name__ == "__main__":
    unittest.main()
